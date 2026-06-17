def parent_unread(request):
    """
    Compteur de notifications non lues — uniquement pour les parents.
    Gate sur le rôle → zéro coût pour les autres utilisateurs.
    """
    if request.user.is_authenticated and request.user.role == 'parent':
        return {
            'parent_unread_count': request.user.notifications.filter(is_read=False).count(),
        }
    return {}


def teacher_unread(request):
    """
    Compteur de notifications non lues — uniquement pour les enseignants.
    Gate sur le rôle → zéro coût pour les autres utilisateurs.
    """
    if request.user.is_authenticated and request.user.role == 'teacher':
        return {
            'teacher_unread_count': request.user.notifications.filter(is_read=False).count(),
        }
    return {}
