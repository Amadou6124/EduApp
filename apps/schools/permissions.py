"""
Helpers de contrôle d'accès pour la saisie des notes.
"""
from apps.accounts.models import UserRole


def can_enter_notes(user, class_subject, period) -> tuple[bool, str]:
    """
    Vérifie si `user` peut saisir des notes pour `class_subject` dans `period`.

    Règles :
    1. Directeur / staff → toujours autorisé (même période fermée).
    2. Superuser → idem directeur.
    3. Enseignant :
       a. La période doit être ouverte (is_notes_open=True).
       b. Il doit être enseignant assigné (ClassSubject.teacher) OU délégué sur la classe.
    4. Tout autre rôle → refusé.

    Retourne (True, None) ou (False, raison_str).
    """
    if user.is_superuser or user.role in (UserRole.DIRECTOR, UserRole.STAFF):
        return True, None

    # Période fermée → seulement le directeur peut forcer
    if not period.is_notes_open:
        return False, 'La saisie des notes est fermée pour cette période.'

    if user.role == UserRole.TEACHER:
        # Enseignant assigné directement à la matière de classe
        if class_subject.teacher_id == user.pk:
            return True, None
        # Ou délégué sur la classe (notes_delegates M2M)
        if class_subject.school_class.notes_delegates.filter(pk=user.pk).exists():
            return True, None
        return False, "Vous n'êtes pas assigné à cette matière pour cette classe."

    return False, "Votre rôle ne permet pas la saisie des notes."
