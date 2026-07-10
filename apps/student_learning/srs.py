"""Répétition espacée (Chantier Révision) — boîtes de Leitner.

Logique pure et testable, aucune vue ici. Principes :
  • La mémoire décide QUAND (courbe d'oubli par concept/élève) ;
    l'emploi du temps ÉCLAIRE l'ordre (bonus « cours demain »), sans jamais contraindre.
  • File du jour FINIE (cap) — usage sain : « c'est assez pour aujourd'hui ».
  • Jamais bloquant : contenu régénéré → ré-ancrage ou suppression silencieuse ;
    matière sans correspondance emploi du temps → simplement pas de bonus.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.lessons.models import LessonDeployment, LessonStatus
from .models import ConceptProgress, ConceptReview

QUEUE_CAP = 6              # concepts max par jour — la file se termine
QUESTIONS_PER_CONCEPT = 2  # questions tirées par concept en session


# ─── Briques internes ─────────────────────────────────────────────────────────

def _active_v2_lessons(student):
    """[(lesson, cv actif)] des leçons v2 READY déployées dans la classe de l'élève."""
    deps = (
        LessonDeployment.objects
        .filter(school_class=student.school_class, is_active=True,
                lesson__status=LessonStatus.READY, lesson__format_version=2)
        .select_related('lesson', 'lesson__active_content_version')
    )
    out, seen = [], set()
    for d in deps:
        if d.lesson_id in seen:
            continue
        seen.add(d.lesson_id)
        cv = d.lesson.active_content_version
        if cv is not None and isinstance(cv.concepts_data, list):
            out.append((d.lesson, cv))
    return out


def _concepts_map(cv):
    """{concept_id: concept} — ids en str, entrées sans id ignorées (défensif)."""
    data = cv.concepts_data if isinstance(cv.concepts_data, list) else []
    return {str(c.get('id')): c for c in data
            if isinstance(c, dict) and c.get('id')}


def _passes_of(concept):
    """Passes déclarés (1..), borné défensivement (contenu IA)."""
    try:
        return max(1, int(concept.get('passes', 1)))
    except (TypeError, ValueError):
        return 1


def state_of(box):
    """Libellé de maîtrise d'une boîte : fragile (1-2), solide (3), maîtrisé (4)."""
    return 'fragile' if box <= 2 else ('solide' if box == 3 else 'maitrise')


# ─── Synchronisation (à l'ouverture de l'onglet — pas de cron) ────────────────

def sync_reviews(student):
    """Aligne l'agenda de mémoire sur l'état réel du parcours.

    1. Dérive de contenu : une ligne ancrée sur une version non-active est
       ré-ancrée si son concept existe encore dans la version active, sinon
       supprimée. Jamais d'erreur, jamais de blocage.
    2. Entrées : chaque concept TERMINÉ (passes_done >= passes) sans agenda
       entre en boîte 1, dû 2 jours après sa complétion (un concept fini il y a
       3 semaines est donc déjà mûr — il apparaît immédiatement).
    """
    for lesson, cv in _active_v2_lessons(student):
        concepts = _concepts_map(cv)

        # 1. dérive : lignes de cette leçon pointant une AUTRE version
        stale = (ConceptReview.objects
                 .filter(student=student, lesson=lesson)
                 .exclude(content_version=cv))
        for r in stale:
            keep = (r.concept_id in concepts and
                    not ConceptReview.objects.filter(
                        student=student, content_version=cv,
                        concept_id=r.concept_id).exists())
            if keep:
                r.content_version = cv
                r.save(update_fields=['content_version'])
            else:
                r.delete()

        # 2. entrées : concepts terminés sans agenda
        existing = set(
            ConceptReview.objects
            .filter(student=student, content_version=cv)
            .values_list('concept_id', flat=True)
        )
        for cp in ConceptProgress.objects.filter(student=student, content_version=cv):
            concept = concepts.get(cp.concept_id)
            if concept is None or cp.concept_id in existing:
                continue
            if cp.passes_done >= _passes_of(concept):
                completed = timezone.localtime(cp.updated_at).date()
                ConceptReview.objects.create(
                    student=student, lesson=lesson, content_version=cv,
                    concept_id=cp.concept_id, box=ConceptReview.BOX_MIN,
                    due_date=completed + timedelta(
                        days=ConceptReview.BOX_INTERVALS[ConceptReview.BOX_MIN]),
                )


# ─── Bonus emploi du temps ────────────────────────────────────────────────────

def subjects_tomorrow(student):
    """{nom de matière en minuscules: heure du 1er cours} pour DEMAIN, d'après
    l'emploi du temps réel de la classe (CourseSlot). Vide si pas d'année active,
    pas de classe, ou pas de cours demain — jamais d'erreur."""
    from apps.schools.models import CourseSlot
    from apps.schools.periods import active_year_for

    if not student.school_class_id:
        return {}
    year = active_year_for(student.school)
    if year is None:
        return {}
    tomorrow = timezone.localdate() + timedelta(days=1)
    slots = (
        CourseSlot.objects
        .filter(school_year=year, day=tomorrow.weekday(),
                class_subject__school_class=student.school_class)
        .select_related('class_subject__subject')
        .order_by('start_time')
    )
    out = {}
    for s in slots:
        name = (s.class_subject.subject.name or '').strip().lower()
        if name and name not in out:
            out[name] = s.start_time
    return out


# ─── File du jour ─────────────────────────────────────────────────────────────

def today_queue(student, cap=QUEUE_CAP):
    """Concepts mûrs (due_date <= aujourd'hui), triés : plus en retard d'abord,
    puis bonus « cours demain » à échéance égale. Bornée à `cap` (usage sain).

    Retourne [{review, concept, name, subject, lesson_title, box, state,
               late_days, tomorrow_time}] — concept = dict du JSON de contenu.
    """
    today = timezone.localdate()
    tomorrow_map = subjects_tomorrow(student)
    items = []
    qs = (ConceptReview.objects
          .filter(student=student, due_date__lte=today)
          .select_related('lesson', 'content_version'))
    for r in qs:
        concept = _concepts_map(r.content_version).get(r.concept_id)
        if concept is None:      # concept disparu sans sync — on l'ignore
            continue
        subject = (r.lesson.subject or '').strip()
        items.append({
            'review': r,
            'concept': concept,
            'name': concept.get('name') or r.concept_id,
            'subject': subject,
            'lesson_title': r.lesson.title,
            'box': r.box,
            'state': state_of(r.box),
            'late_days': (today - r.due_date).days,
            'tomorrow_time': tomorrow_map.get(subject.lower()),
        })
    items.sort(key=lambda i: (i['review'].due_date,
                              0 if i['tomorrow_time'] else 1,
                              i['review'].concept_id))
    return items[:cap]


def due_count(student):
    """Nombre de concepts mûrs — pastille de l'onglet Révision."""
    return ConceptReview.objects.filter(
        student=student, due_date__lte=timezone.localdate()).count()


# ─── Résultat d'une révision ──────────────────────────────────────────────────

def apply_result(review, success):
    """Réussite → boîte +1 ; échec → boîte -1 (bornée 1..4, jamais punitif).
    La prochaine date part d'AUJOURD'HUI + intervalle de la nouvelle boîte."""
    if success:
        review.box = min(ConceptReview.BOX_MAX, review.box + 1)
    else:
        review.box = max(ConceptReview.BOX_MIN, review.box - 1)
    review.due_date = (timezone.localdate() +
                       timedelta(days=ConceptReview.BOX_INTERVALS[review.box]))
    review.last_reviewed_at = timezone.now()
    review.save(update_fields=['box', 'due_date', 'last_reviewed_at'])
    return review


# ─── Tableaux de bord (jauges + aperçu) ───────────────────────────────────────

def garden_counts(student):
    """Jauges « Ta mémoire » : {'fragile': n, 'solide': n, 'maitrise': n}."""
    return ConceptReview.objects.filter(student=student).aggregate(
        fragile=Count('id', filter=Q(box__lte=2)),
        solide=Count('id', filter=Q(box=3)),
        maitrise=Count('id', filter=Q(box__gte=4)),
    )


def next_days_preview(student, limit=2):
    """Aperçu des prochains jours (état « tout est frais ») :
    [{date, count, subjects: [noms]}] trié par date, `limit` premiers jours."""
    today = timezone.localdate()
    groups = {}
    qs = (ConceptReview.objects
          .filter(student=student, due_date__gt=today)
          .select_related('lesson')
          .order_by('due_date'))
    for r in qs:
        g = groups.setdefault(r.due_date, {'date': r.due_date, 'count': 0, 'subjects': []})
        g['count'] += 1
        subject = (r.lesson.subject or '').strip()
        if subject and subject not in g['subjects']:
            g['subjects'].append(subject)
    return [groups[d] for d in sorted(groups)][:limit]
