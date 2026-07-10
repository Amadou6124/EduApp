"""Usage sain (Chantier « Mon rythme ») — logique pure, testable.

Philosophie gravée : on optimise le temps EFFICACE, pas le temps passé.
  • UN objectif quotidien, modeste et FINI : la file de révision du jour (déjà
    bornée à 6). Quand c'est fait, l'app dit STOP — jamais « encore ».
  • La semaine en 7 pastilles SANS punition : un jour vide n'est jamais un
    reproche, pas de « série brisée », pas de flamme qui meurt.
  • Bienveillance nocturne : tard le soir on souhaite bonne nuit, on ne pousse pas.
  • Côté parent : le VRAI travail (jours actifs, notions consolidées, cahier à la
    main) — jamais « X heures d'écran » présenté comme un trophée.
"""
from datetime import timedelta, time

from django.utils import timezone

from .models import CahierAttempt, ConceptReview, ExamAttempt, QuizAttempt, StoryAttempt
from .srs import QUEUE_CAP, due_count

# Nuit « bienveillante » : de 21h30 à 5h du matin.
NIGHT_START = time(21, 30)
NIGHT_END = time(5, 0)

_DAY_LABELS = ['L', 'M', 'M', 'J', 'V', 'S', 'D']   # lundi → dimanche


# ─── Activité datée (toutes surfaces confondues) ─────────────────────────────

def _activity_dates(student, since_date):
    """Dates locales (>= since_date) où l'élève a fait AU MOINS une action
    d'apprentissage : réponse de quiz/révision, cahier, histoire, examen."""
    dates = set()
    pairs = [
        (QuizAttempt, 'attempted_at'),
        (CahierAttempt, 'completed_at'),
        (StoryAttempt, 'completed_at'),
        (ExamAttempt, 'started_at'),
    ]
    for model, field in pairs:
        qs = (model.objects
              .filter(student=student, **{f'{field}__date__gte': since_date})
              .values_list(field, flat=True))
        for dt in qs:
            dates.add(timezone.localtime(dt).date())
    return dates


def week_strip(student, today=None):
    """Les 7 pastilles de la semaine courante (lundi → dimanche).

    [{label, date, active, is_today, future}] — un jour vide reste neutre
    (aucune notion d'échec) ; les jours à venir sont marqués future."""
    today = today or timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    actives = _activity_dates(student, monday)
    strip = []
    for i in range(7):
        d = monday + timedelta(days=i)
        strip.append({
            'label': _DAY_LABELS[i],
            'date': d,
            'active': d in actives,
            'is_today': d == today,
            'future': d > today,
        })
    return strip


# ─── Objectif du jour (la file de révision, déjà bornée) ─────────────────────

def daily_goal(student, today=None):
    """L'objectif quotidien UNIQUE : faire sa file de révision du jour.

    Retourne {state, done, total, remaining} :
      state = 'todo'  — il reste des concepts mûrs à réviser
              'done'  — la file du jour est terminée (l'app dit STOP)
              'fresh' — rien n'était mûr aujourd'hui (tout est frais)
    total est borné à QUEUE_CAP (la file est FINIE par construction)."""
    today = today or timezone.localdate()
    done_today = ConceptReview.objects.filter(
        student=student, last_reviewed_at__date=today).count()
    remaining = due_count(student)

    total = min(QUEUE_CAP, done_today + remaining)
    done = min(done_today, total)

    if remaining > 0:
        state = 'todo'
    elif done_today > 0:
        state = 'done'
    else:
        state = 'fresh'
    return {'state': state, 'done': done, 'total': total,
            'remaining': min(remaining, QUEUE_CAP)}


def is_night(now=None):
    """Vrai entre 21h30 et 5h (heure locale) — le moment du message bonne nuit."""
    now = timezone.localtime(now or timezone.now()).time()
    return now >= NIGHT_START or now < NIGHT_END


# ─── Résumé hebdo côté parent (le VRAI travail) ──────────────────────────────

def week_summary(student, today=None):
    """La semaine de l'enfant, en travail réel (pas en temps d'écran) :
    {strip, active_days, concepts_reviewed, consolidated, cahier_count}.

      concepts_reviewed — concepts dont la DERNIÈRE révision date de cette
        semaine (approximation honnête : pas d'historique de boîtes en base).
      consolidated — parmi eux, ceux aujourd'hui solides/maîtrisés (boîte >= 3).
    """
    today = today or timezone.localdate()
    monday = today - timedelta(days=today.weekday())

    strip = week_strip(student, today)
    reviewed = ConceptReview.objects.filter(
        student=student, last_reviewed_at__date__gte=monday)

    return {
        'strip': strip,
        'active_days': sum(1 for d in strip if d['active']),
        'concepts_reviewed': reviewed.count(),
        'consolidated': reviewed.filter(box__gte=3).count(),
        'cahier_count': CahierAttempt.objects.filter(
            student=student, completed_at__date__gte=monday).count(),
    }
