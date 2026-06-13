from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

from apps.schools.models import ClassSubject, Note
from .models import QuickAssessment


# ─── Constantes ──────────────────────────────────────────────────────────────

WEIGHT_OFFICIAL = Decimal('0.60')
WEIGHT_QUICK    = Decimal('0.40')

LEVEL_CRITICAL = 'critical'
LEVEL_WARNING  = 'warning'
LEVEL_WATCH    = 'watch'
LEVEL_GOOD     = 'good'

TREND_THRESHOLD = Decimal('1.5')


def _normalize(value, max_value) -> Decimal:
    """Ramène n'importe quelle note sur /20."""
    if not max_value:
        return Decimal('0')
    return (Decimal(str(value)) / Decimal(str(max_value)) * Decimal('20')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )


def _avg(values: list) -> Decimal | None:
    if not values:
        return None
    return (sum(values) / len(values)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _trend(scores_chrono: list) -> str:
    """
    Comparaison moyenne 3 premières évals vs 3 dernières.
    scores_chrono trié du plus ancien au plus récent.
    """
    if len(scores_chrono) < 2:
        return 'stable'
    first = _avg(scores_chrono[:3])
    last  = _avg(scores_chrono[-3:])
    if first is None or last is None:
        return 'stable'
    diff = last - first
    if diff < -TREND_THRESHOLD:
        return 'down'
    if diff > TREND_THRESHOLD:
        return 'up'
    return 'stable'


def _score_level(score: Decimal) -> str:
    if score < Decimal('8'):
        return LEVEL_CRITICAL
    if score < Decimal('10'):
        return LEVEL_WARNING
    if score < Decimal('12'):
        return LEVEL_WATCH
    return LEVEL_GOOD


# ─── Score par élève × matière ───────────────────────────────────────────────

def compute_difficulty_score(
    student,
    teacher,
    class_subject,
    period,
    *,
    notes_by_cs: dict | None = None,
    qa_by_cs: dict | None = None,
) -> dict:
    """
    Score de difficulté pour un élève dans une matière sur une période.

    notes_by_cs / qa_by_cs : dicts pré-chargés {cs_id: [objet, ...]}
    Si None → requêtes individuelles (mode fiche élève isolée).
    """
    # ── Notes officielles ────────────────────────────────────────
    if notes_by_cs is not None:
        raw_notes = notes_by_cs.get(class_subject.pk, [])
    else:
        raw_notes = list(
            Note.objects.filter(
                class_subject=class_subject,
                student=student,
                period=period,
                is_cancelled=False,
            ).order_by('position')
        )

    official_norm = [_normalize(n.value, class_subject.max_grade) for n in raw_notes]
    official_avg  = _avg(official_norm)

    # ── Évaluations rapides ──────────────────────────────────────
    if qa_by_cs is not None:
        raw_qa = qa_by_cs.get(class_subject.pk, [])
    else:
        raw_qa = list(
            QuickAssessment.objects.filter(
                class_subject=class_subject,
                student=student,
                period=period,
                teacher=teacher,
            ).order_by('assessed_at', 'created_at')
        )

    quick_norm = [_normalize(qa.value, qa.max_value) for qa in raw_qa]
    quick_avg  = _avg(quick_norm)

    # ── Score pondéré ────────────────────────────────────────────
    if official_avg is not None and quick_avg is not None:
        score = (
            official_avg * WEIGHT_OFFICIAL + quick_avg * WEIGHT_QUICK
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    elif official_avg is not None:
        score = official_avg
    elif quick_avg is not None:
        score = quick_avg
    else:
        score = None

    # ── Tendance : fusion chrono notes + évals rapides ───────────
    all_chrono = sorted(
        [(n.entered_at, _normalize(n.value, class_subject.max_grade)) for n in raw_notes]
        + [(qa.assessed_at, _normalize(qa.value, qa.max_value)) for qa in raw_qa],
        key=lambda t: t[0],
    )
    trend = _trend([v for _, v in all_chrono]) if len(all_chrono) >= 2 else 'stable'

    return {
        'score':             score,
        'level':             _score_level(score) if score is not None else None,
        'official_avg':      official_avg,
        'quick_avg':         quick_avg,
        'trend':             trend,
        'assessments_count': len(raw_qa),
        'notes_count':       len(raw_notes),
    }


# ─── Rapport complet d'une classe ────────────────────────────────────────────

def get_class_difficulty_report(teacher, school_class, period) -> list:
    """
    Rapport trié par score global ascendant (pire élève en premier).
    2 requêtes SQL pour toute la classe — zéro N+1.
    """
    my_cs = list(
        ClassSubject.objects.filter(
            school_class=school_class,
            teacher=teacher,
            is_active=True,
        ).select_related('subject').order_by('order', 'subject__name')
    )
    if not my_cs:
        return []

    cs_ids = [cs.pk for cs in my_cs]

    # Requête 1 — notes officielles
    notes_map: dict = defaultdict(lambda: defaultdict(list))
    for n in (
        Note.objects
        .filter(class_subject_id__in=cs_ids, period=period, is_cancelled=False)
        .select_related('student')
        .order_by('position')
    ):
        notes_map[n.student_id][n.class_subject_id].append(n)

    # Requête 2 — évaluations rapides
    qa_map: dict = defaultdict(lambda: defaultdict(list))
    for qa in (
        QuickAssessment.objects
        .filter(class_subject_id__in=cs_ids, period=period, teacher=teacher)
        .select_related('student')
        .order_by('assessed_at', 'created_at')
    ):
        if qa.student_id:
            qa_map[qa.student_id][qa.class_subject_id].append(qa)

    from apps.students.models import Student
    students = list(
        Student.objects.filter(school_class=school_class, is_active=True).order_by('full_name')
    )

    results = []
    for student in students:
        cs_scores = {}
        subject_scores = []

        for cs in my_cs:
            score_dict = compute_difficulty_score(
                student=student,
                teacher=teacher,
                class_subject=cs,
                period=period,
                notes_by_cs={cs.pk: notes_map[student.pk].get(cs.pk, [])},
                qa_by_cs={cs.pk: qa_map[student.pk].get(cs.pk, [])},
            )
            score_dict['cs_id'] = cs.pk  # requis pour le formulaire d'éval rapide
            cs_scores[cs.subject.name] = score_dict
            if score_dict['score'] is not None:
                subject_scores.append(score_dict['score'])

        global_score = _avg(subject_scores)
        global_level = _score_level(global_score) if global_score is not None else None

        trends = [v['trend'] for v in cs_scores.values()]
        if 'down' in trends:
            global_trend = 'down'
        elif 'up' in trends and 'stable' not in trends:
            global_trend = 'up'
        else:
            global_trend = 'stable'

        results.append({
            'student':      student,
            'scores':       cs_scores,
            'global_score': global_score,
            'level':        global_level,
            'trend':        global_trend,
        })

    results.sort(
        key=lambda r: r['global_score'] if r['global_score'] is not None else Decimal('99')
    )
    return results
