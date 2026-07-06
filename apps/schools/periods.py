"""
Résolution centralisée des périodes d'évaluation — **par cycle**.

Contexte : une même école peut avoir des rythmes différents selon le cycle
(compositions au fondamental, trimestres au secondaire). Ce module est la
*source unique* : au lieu de `year.periods.all()`, une vue demande les périodes
**d'une classe** (ou d'un élève) et obtient celles de son cycle.

Rétro-compatibilité : si un cycle n'a pas de périodes propres, on retombe sur
les périodes « sans cycle » (`education_level IS NULL`) de l'année — c'est le
comportement historique des écoles mono-structure.

Architecture : le résolveur prend une *classe* en entrée (pas un cycle brut).
Passer plus tard à une grille fine par classe = changer l'intérieur de ce
module, PAS les points d'appel.
"""
from .models import Period, SchoolYear


def active_year_for(school):
    """Année scolaire active d'une école (fallback : la plus récente)."""
    if school is None:
        return None
    return (
        school.school_years.filter(is_active=True).first()
        or school.school_years.order_by('-start_date').first()
    )


def periods_for_cycle(school_year, education_level):
    """Périodes d'une année pour un cycle donné, ordonnées.

    Fallback : si le cycle n'a pas de périodes propres, renvoie les périodes
    sans cycle (NULL) de l'année.
    """
    if school_year is None:
        return Period.objects.none()
    scoped = school_year.periods.filter(education_level=education_level).order_by('order')
    if scoped.exists():
        return scoped
    return school_year.periods.filter(education_level__isnull=True).order_by('order')


def periods_for_class(school_class, school_year=None):
    """Périodes applicables à une classe (selon son cycle `level`)."""
    if school_class is None:
        return Period.objects.none()
    year = school_year or active_year_for(school_class.school)
    return periods_for_cycle(year, school_class.level)


def periods_for_student(student, school_year=None):
    """Périodes applicables à un élève (via sa classe courante)."""
    school_class = getattr(student, 'school_class', None)
    return periods_for_class(school_class, school_year)


def resolve_active_period(periods, requested_pk=None, prefer='open'):
    """Choisit la période courante dans une liste **déjà résolue** (par cycle).

    Priorité : période demandée (`requested_pk`) → puis la stratégie `prefer` :
      - 'open'  : la période à saisie ouverte, sinon la dernière (ordre max) ;
      - 'first' : la première période (usage bulletins).
    Renvoie None si la liste est vide.
    """
    periods = list(periods)
    if not periods:
        return None
    if requested_pk:
        for p in periods:
            if str(p.pk) == str(requested_pk):
                return p
    if prefer == 'first':
        return periods[0]
    for p in periods:
        if p.is_notes_open:
            return p
    return periods[-1]
