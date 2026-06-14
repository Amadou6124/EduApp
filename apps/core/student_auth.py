"""
Auth portail élève — session isolée du système User (parent/prof).

L'élève n'est PAS un User Django : il reste un students.Student.
Sa session vit sous une clé dédiée (STUDENT_SESSION_KEY), exposée en
request.student via @student_required — jamais request.user. Parent/prof
et élève peuvent donc coexister sur le même navigateur sans collision.
"""
from functools import wraps

from django.shortcuts import redirect
from django.utils import timezone

from apps.students.models import Student

STUDENT_SESSION_KEY = 'student_id'


def _name_matches(full_name, typed):
    """Vrai si `typed` correspond à un token du nom complet (nom malien souvent en premier)."""
    if not full_name or not typed:
        return False
    tokens = [t.lower() for t in full_name.split()]
    return typed.strip().lower() in tokens


def authenticate_student(access_code, last_name, password=None):
    """
    Vérifie les identifiants élève. access_code unique seulement par école →
    on désambiguïse par nom de famille. Retourne le Student si UN SEUL match, sinon None.
    """
    if not access_code:
        return None

    matches = []
    for s in Student.objects.select_related('school', 'school_class').filter(
        access_code=access_code, is_active=True,
    ):
        if not _name_matches(s.full_name, last_name):
            continue
        # Mot de passe optionnel : si défini sur la fiche, il doit correspondre.
        if s.password and password and not s.check_student_password(password):
            continue
        matches.append(s)

    return matches[0] if len(matches) == 1 else None


def login_student(request, student):
    """Ouvre la session élève (clé dédiée, n'écrase pas request.user)."""
    request.session[STUDENT_SESSION_KEY] = student.pk
    student.last_login = timezone.now()
    student.save(update_fields=['last_login'])


def logout_student(request):
    """Ferme la session élève sans toucher à une éventuelle session parent/prof."""
    request.session.pop(STUDENT_SESSION_KEY, None)


def student_required(view_func):
    """Charge request.student depuis la session ou redirige vers le login élève."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        sid = request.session.get(STUDENT_SESSION_KEY)
        if not sid:
            return redirect('learn:login')
        try:
            request.student = Student.objects.select_related(
                'school', 'school_class',
            ).get(pk=sid, is_active=True)
        except Student.DoesNotExist:
            request.session.pop(STUDENT_SESSION_KEY, None)
            return redirect('learn:login')
        return view_func(request, *args, **kwargs)
    return wrapper
