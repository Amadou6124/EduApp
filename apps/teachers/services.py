from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
from datetime import date as _date

from apps.schools.models import ClassSubject, Note, FormativeGrade


# ─── Constantes ──────────────────────────────────────────────────────────────

WEIGHT_OFFICIAL  = Decimal('0.60')
WEIGHT_FORMATIVE = Decimal('0.40')

LEVEL_CRITICAL     = 'critical'      # < 8  → en difficulté
LEVEL_WARNING      = 'warning'       # < 12 → à surveiller
LEVEL_GOOD         = 'good'          # >= 12
LEVEL_INSUFFICIENT = 'insufficient'  # < 2 données → pas assez pour juger

MIN_DATA_POINTS = 2
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
    """Moyenne des 3 premières évals vs 3 dernières (chrono ancien→récent)."""
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
    if score < Decimal('12'):
        return LEVEL_WARNING
    return LEVEL_GOOD


# ─── Score par élève × matière ───────────────────────────────────────────────

def compute_difficulty_score(
    student,
    teacher,
    class_subject,
    period,
    *,
    notes_by_cs: dict | None = None,
    fg_by_cs: dict | None = None,
) -> dict:
    """
    Score de difficulté d'un élève dans une matière sur une période.

    Source unique du signal formatif : FormativeGrade (l'onglet « Formatif » de
    la page Notes) — plus de QuickAssessment. On mêle notes officielles (60 %)
    et formatif (40 %). En dessous de MIN_DATA_POINTS données, l'élève n'est pas
    jugé (niveau « insufficient ») pour éviter les fausses alertes.

    notes_by_cs : {cs_id: [Note, ...]}
    fg_by_cs    : {cs_id: [(value, max_grade, date), ...]}
    Si None → requêtes individuelles (fiche élève isolée).
    """
    # ── Notes officielles ────────────────────────────────────────
    if notes_by_cs is not None:
        raw_notes = notes_by_cs.get(class_subject.pk, [])
    else:
        raw_notes = list(
            Note.objects.filter(
                class_subject=class_subject, student=student,
                period=period, is_cancelled=False,
            ).order_by('position')
        )
    official_norm = [_normalize(n.value, class_subject.max_grade) for n in raw_notes]
    official_avg  = _avg(official_norm)

    # ── Notes formatives (source unique du formatif) ─────────────
    if fg_by_cs is not None:
        raw_fg = fg_by_cs.get(class_subject.pk, [])
    else:
        raw_fg = list(
            FormativeGrade.objects.filter(
                evaluation__class_subject=class_subject,
                evaluation__period=period,
                student=student, is_absent=False, value__isnull=False,
            ).values_list('value', 'evaluation__max_grade', 'evaluation__date')
        )
    formative_norm = [_normalize(v, mx) for (v, mx, _d) in raw_fg]
    formative_avg  = _avg(formative_norm)

    data_points = len(official_norm) + len(formative_norm)

    # ── Score pondéré ────────────────────────────────────────────
    if official_avg is not None and formative_avg is not None:
        score = (
            official_avg * WEIGHT_OFFICIAL + formative_avg * WEIGHT_FORMATIVE
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    elif official_avg is not None:
        score = official_avg
    elif formative_avg is not None:
        score = formative_avg
    else:
        score = None

    # ── Niveau (garde-fou anti fausses alertes) ──────────────────
    if score is None or data_points == 0:
        level = None
    elif data_points < MIN_DATA_POINTS:
        level = LEVEL_INSUFFICIENT
    else:
        level = _score_level(score)

    # ── Tendance : notes + formatif, du plus ancien au plus récent ──
    chrono = sorted(
        [(n.entered_at.date() if n.entered_at else None,
          _normalize(n.value, class_subject.max_grade)) for n in raw_notes]
        + [(d, _normalize(v, mx)) for (v, mx, d) in raw_fg],
        key=lambda t: (t[0] is None, t[0] or _date.min),
    )
    trend = _trend([v for _, v in chrono]) if len(chrono) >= 2 else 'stable'

    return {
        'score':           score,
        'level':           level,
        'official_avg':    official_avg,
        'formative_avg':   formative_avg,
        'trend':           trend,
        'data_points':     data_points,
        'formative_count': len(formative_norm),
        'notes_count':     len(official_norm),
    }


def student_attention_subjects(student, period):
    """Matières où l'élève est en difficulté CRITIQUE sur la période (suivi précoce).

    Source unique du signal « point d'attention », partagée par la page Scolarité
    (bannière) et le dashboard parent (fil d'alertes). S'appuie sur
    compute_difficulty_score (mêmes seuils / garde-fou anti-fausse-alerte).
    Retourne la liste des noms de matières (vide si période absente / pas assez de
    données). ~2 requêtes par élève.
    """
    from collections import defaultdict
    from apps.schools.models import Note, FormativeGrade

    if period is None:
        return []

    notes_by_cs = defaultdict(list)
    cs_by_id = {}
    for n in (Note.objects
              .filter(student=student, period=period, is_cancelled=False)
              .select_related('class_subject', 'class_subject__subject')):
        notes_by_cs[n.class_subject_id].append(n)
        cs_by_id[n.class_subject_id] = n.class_subject
    if not cs_by_id:
        return []

    fg_by_cs = defaultdict(list)
    for v, mx, d, cs_id in (FormativeGrade.objects
                            .filter(student=student, evaluation__period=period,
                                    is_absent=False, value__isnull=False)
                            .values_list('value', 'evaluation__max_grade',
                                         'evaluation__date', 'evaluation__class_subject')):
        fg_by_cs[cs_id].append((v, mx, d))

    out = []
    for cs_id, cs in cs_by_id.items():
        diff = compute_difficulty_score(
            student, None, cs, period, notes_by_cs=notes_by_cs, fg_by_cs=fg_by_cs,
        )
        if diff['level'] == LEVEL_CRITICAL:
            out.append(cs.subject.name)
    return out


# ─── Rapport complet d'une classe ────────────────────────────────────────────

def get_class_difficulty_report(teacher, school_class, period) -> list:
    """Rapport par élève (pire d'abord). 3 requêtes SQL pour toute la classe."""
    my_cs = list(
        ClassSubject.objects.filter(
            school_class=school_class, teacher=teacher, is_active=True,
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
        .order_by('position')
    ):
        notes_map[n.student_id][n.class_subject_id].append(n)

    # Requête 2 — notes formatives (valeurs brutes)
    fg_map: dict = defaultdict(lambda: defaultdict(list))
    for sid, csid, val, mx, d in (
        FormativeGrade.objects
        .filter(evaluation__class_subject_id__in=cs_ids, evaluation__period=period,
                is_absent=False, value__isnull=False)
        .values_list('student_id', 'evaluation__class_subject_id',
                     'value', 'evaluation__max_grade', 'evaluation__date')
    ):
        fg_map[sid][csid].append((val, mx, d))

    from apps.students.models import Student
    students = list(
        Student.objects.filter(school_class=school_class, is_active=True).order_by('full_name')
    )

    results = []
    for student in students:
        cs_scores = {}
        judged_scores = []

        for cs in my_cs:
            sd = compute_difficulty_score(
                student=student, teacher=teacher, class_subject=cs, period=period,
                notes_by_cs={cs.pk: notes_map[student.pk].get(cs.pk, [])},
                fg_by_cs={cs.pk: fg_map[student.pk].get(cs.pk, [])},
            )
            sd['cs_id']   = cs.pk
            sd['subject'] = cs.subject.name
            cs_scores[cs.subject.name] = sd
            if sd['level'] in (LEVEL_CRITICAL, LEVEL_WARNING, LEVEL_GOOD):
                judged_scores.append(sd['score'])

        if judged_scores:
            global_score = _avg(judged_scores)
            global_level = _score_level(global_score)
        elif any(v['level'] == LEVEL_INSUFFICIENT for v in cs_scores.values()):
            global_score, global_level = None, LEVEL_INSUFFICIENT
        else:
            global_score, global_level = None, None  # aucune donnée → ignoré

        judged_trends = [v['trend'] for v in cs_scores.values()
                         if v['level'] in (LEVEL_CRITICAL, LEVEL_WARNING, LEVEL_GOOD)]
        if 'down' in judged_trends:
            global_trend = 'down'
        elif 'up' in judged_trends and 'stable' not in judged_trends:
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
