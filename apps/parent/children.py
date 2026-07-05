"""Enfants d'un parent + enfant actif — source unique.

L'enfant actif est mémorisé en SESSION (plus l'URL) : choisi une fois dans la
pastille du header, il persiste d'un onglet à l'autre. `?child=<id>` reste le
mécanisme de sélection (il écrit la session).
"""
SESSION_KEY = 'parent_active_child'


def parent_students(user):
    """Élèves sous la garde du parent (sécurisé via guarded_students), ordonnés
    parent principal d'abord puis par nom."""
    return [
        link.student
        for link in (
            user.guarded_students
            .select_related('student', 'student__school', 'student__school_class')
            .order_by('-is_primary', 'student__full_name')
        )
    ]


def resolve_active_child(request, students):
    """Enfant actif : `?child=` (persiste en session) → session → premier enfant.
    Retourne le Student actif, ou None si aucun enfant lié."""
    if not students:
        return None
    ids = [s.id for s in students]

    req = request.GET.get('child')
    if req and req.isdigit() and int(req) in ids:
        request.session[SESSION_KEY] = int(req)
        return next(s for s in students if s.id == int(req))

    sess = request.session.get(SESSION_KEY)
    if sess in ids:
        return next(s for s in students if s.id == sess)

    request.session[SESSION_KEY] = ids[0]
    return students[0]
