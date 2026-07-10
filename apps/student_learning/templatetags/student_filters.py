from django import template

register = template.Library()


@register.filter
def dict_key(d, key):
    """Accès dict[key] dans un template (clé dynamique)."""
    if not d:
        return None
    return d.get(key)


@register.simple_tag(takes_context=True)
def revision_due_count(context):
    """Pastille de l'onglet Révision (nav élève) : nombre de concepts mûrs.
    Défensif : 0 si pas d'élève en contexte — la nav ne casse jamais."""
    request = context.get('request')
    student = getattr(request, 'student', None)
    if student is None:
        return 0
    try:
        from apps.student_learning import srs
        return srs.due_count(student)
    except Exception:
        return 0
