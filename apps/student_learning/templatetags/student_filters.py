from django import template

register = template.Library()


@register.filter
def dict_key(d, key):
    """Accès dict[key] dans un template (clé dynamique)."""
    if not d:
        return None
    return d.get(key)
