"""Helpers de création de notifications. Producteurs : teachers, schools, payments."""
from django.contrib.contenttypes.models import ContentType

from .models import Notification, NotificationCategory  # noqa: F401 (réexport pratique)


def _target_fields(target):
    if target is None:
        return None, None
    return ContentType.objects.get_for_model(target.__class__), target.pk


def notify(recipient, school, category, title, body='', url='', target=None, student=None):
    """Crée une notification pour UN utilisateur."""
    ct, oid = _target_fields(target)
    return Notification.objects.create(
        recipient=recipient, school=school, category=category,
        title=title, body=body, url=url,
        content_type=ct, object_id=oid, student=student,
    )


def notify_guardians(student, category, title, body='', url='', target=None):
    """
    Notifie TOUS les parents/tuteurs d'un élève (bulk_create → 1 insert).
    L'école est dérivée de l'élève. Zéro N+1.
    """
    from apps.students.models import StudentGuardian

    guardian_ids = list(
        StudentGuardian.objects.filter(student=student)
        .values_list('guardian_id', flat=True)
    )
    if not guardian_ids:
        return []
    ct, oid = _target_fields(target)
    notifs = [
        Notification(
            recipient_id=gid, school=student.school, category=category,
            title=title, body=body, url=url, content_type=ct, object_id=oid,
            student=student,
        )
        for gid in guardian_ids
    ]
    return Notification.objects.bulk_create(notifs)
