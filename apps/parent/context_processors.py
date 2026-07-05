"""Header global du portail parent — enfants liés + enfant actif.

Rend `parent_children` + `parent_active_child` disponibles sur TOUTES les pages
parent (pour le header unifié), sans que chaque vue ait à les fournir.
"""
from apps.accounts.models import UserRole
from apps.parent.children import parent_students, resolve_active_child


def parent_header(request):
    """Gate sur le rôle parent → zéro coût pour les autres utilisateurs."""
    if not (request.user.is_authenticated
            and getattr(request.user, 'role', None) == UserRole.PARENT):
        return {}
    students = parent_students(request.user)
    return {
        'parent_children': students,
        'parent_active_child': resolve_active_child(request, students),
    }
