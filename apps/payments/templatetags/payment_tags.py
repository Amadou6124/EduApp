from django import template

register = template.Library()


@register.filter
def fcfa_fmt(value):
    """Formate un montant FCFA avec espace comme séparateur de milliers.
    1250000 → '1 250 000'
    """
    try:
        n = int(value)
        return f'{n:,}'.replace(',', '\u202f')
    except (TypeError, ValueError):
        return str(value)


@register.filter
def fcfa_compact(value):
    """Version courte pour petits écrans.
    1250000 → '1,25M'
    125000  → '125k'
    9500    → '9 500'
    """
    try:
        n = int(value)
        if n >= 1_000_000:
            m = n / 1_000_000
            formatted = f'{m:.2f}'.rstrip('0').rstrip('.')
            return f'{formatted}M'.replace('.', ',')
        if n >= 10_000:
            k = n / 1_000
            formatted = f'{k:.1f}'.rstrip('0').rstrip('.')
            return f'{formatted}k'.replace('.', ',')
        return f'{n:,}'.replace(',', '\u202f')
    except (TypeError, ValueError):
        return str(value)
