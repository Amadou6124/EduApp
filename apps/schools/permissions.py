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

    if user.role == UserRole.TEACHER:
        # 1. Doit être assigné (enseignant de la matière) ou délégué sur la classe.
        assigned = (
            class_subject.teacher_id == user.pk
            or class_subject.school_class.notes_delegates.filter(pk=user.pk).exists()
        )
        if not assigned:
            return False, "Vous n'êtes pas assigné à cette matière pour cette classe."
        # 2. Période ouverte globalement OU ouverture ciblée accordée par le directeur.
        if period.is_notes_open:
            return True, None
        grant = (
            class_subject.entry_grants
            .filter(period=period)
            .first()
        )
        if grant and grant.is_active():
            return True, None
        return False, 'La saisie des notes est fermée pour cette période.'

    return False, "Votre rôle ne permet pas la saisie des notes."


def can_enter_formatif(user, class_subject) -> bool:
    """Flux formatif (hors bulletin) : l'enseignant assigné/délégué saisit à tout
    moment (outil de suivi continu, sans gate de période). Directeur/staff : toujours."""
    if user.is_superuser or user.role in (UserRole.DIRECTOR, UserRole.STAFF):
        return True
    if user.role == UserRole.TEACHER:
        return (
            class_subject.teacher_id == user.pk
            or class_subject.school_class.notes_delegates.filter(pk=user.pk).exists()
        )
    return False
