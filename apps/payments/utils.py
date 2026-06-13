"""
amount_to_words_fr — conversion d'un montant FCFA en lettres françaises.

Règles orthographiques appliquées :
  - "vingt et un", "trente et un" … "soixante et un", "soixante et onze"
  - "quatre-vingts" (avec s) seul ou devant mille/million
  - "quatre-vingt"  (sans s) suivi d'un nombre (81-89)
  - "cent"   invariable quand suivi d'un nombre (201 → deux cent un)
  - "cents"  pluriel quand seul ou devant mille/million (200 → deux cents)
  - "mille"  toujours invariable
  - "million(s)" prend le s à partir de 2
  - Maximum supporté : 99 999 999 FCFA
"""

_UNITS = [
    '', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf',
    'dix', 'onze', 'douze', 'treize', 'quatorze', 'quinze', 'seize',
    'dix-sept', 'dix-huit', 'dix-neuf',
]


def _below_100(n: int, terminal: bool = True) -> str:
    """
    Convertit 1-99 en lettres.
    terminal=True → quatre-vingts avec s quand n==80 (rien ne suit ce groupe).
    """
    if n < 20:
        return _UNITS[n]
    t, u = divmod(n, 10)
    if t == 2:
        if u == 0: return 'vingt'
        if u == 1: return 'vingt et un'
        return f'vingt-{_UNITS[u]}'
    if t == 3:
        if u == 0: return 'trente'
        if u == 1: return 'trente et un'
        return f'trente-{_UNITS[u]}'
    if t == 4:
        if u == 0: return 'quarante'
        if u == 1: return 'quarante et un'
        return f'quarante-{_UNITS[u]}'
    if t == 5:
        if u == 0: return 'cinquante'
        if u == 1: return 'cinquante et un'
        return f'cinquante-{_UNITS[u]}'
    if t == 6:
        if u == 0: return 'soixante'
        if u == 1: return 'soixante et un'
        return f'soixante-{_UNITS[u]}'
    if t == 7:
        if u == 0: return 'soixante-dix'
        if u == 1: return 'soixante et onze'
        return f'soixante-{_UNITS[10 + u]}'
    if t == 8:
        if u == 0: return 'quatre-vingts' if terminal else 'quatre-vingt'
        return f'quatre-vingt-{_UNITS[u]}'
    # t == 9
    if u == 0: return 'quatre-vingt-dix'
    return f'quatre-vingt-{_UNITS[10 + u]}'


def _below_1000(n: int, terminal: bool = True) -> str:
    """
    Convertit 1-999 en lettres.
    terminal=True → deux cents / cinq cents avec s quand r==0.
    """
    if n < 100:
        return _below_100(n, terminal=terminal)
    h, r = divmod(n, 100)
    if h == 1:
        if r == 0:
            return 'cent'
        return f'cent {_below_100(r)}'
    h_word = _UNITS[h]
    if r == 0:
        return f'{h_word} cent{"s" if terminal else ""}'
    return f'{h_word} cent {_below_100(r)}'


def amount_to_words_fr(amount) -> str:
    """
    Convertit un montant FCFA en lettres françaises.
    Accepte int ou Decimal. Maximum : 99 999 999 FCFA.

    Exemples :
        0         → "Zéro Franc CFA"
        1         → "Un Franc CFA"
        25 000    → "Vingt-cinq mille Francs CFA"
        75 500    → "Soixante-quinze mille cinq cents Francs CFA"
        80 000    → "Quatre-vingts mille Francs CFA"
        150 000   → "Cent cinquante mille Francs CFA"
        200 000   → "Deux cents mille Francs CFA"
        1 000 000 → "Un million Francs CFA"
        2 500 000 → "Deux millions cinq cents mille Francs CFA"
    """
    amount = int(amount)
    if amount < 0:
        raise ValueError(f'Montant négatif non supporté : {amount}')
    if amount > 99_999_999:
        raise ValueError(f'{amount} dépasse le maximum supporté (99 999 999 FCFA)')

    if amount == 0:
        return 'Zéro Franc CFA'

    millions  = amount  // 1_000_000
    rem_m     = amount  %  1_000_000
    thousands = rem_m   // 1_000
    remainder = rem_m   %  1_000

    parts = []

    if millions:
        if millions == 1:
            parts.append('un million')
        else:
            parts.append(f'{_below_100(millions)} millions')

    if thousands:
        if thousands == 1:
            parts.append('mille')
        else:
            parts.append(f'{_below_1000(thousands)} mille')

    if remainder:
        parts.append(_below_1000(remainder))

    words = ' '.join(parts)
    words = words[0].upper() + words[1:]
    franc = 'Franc' if amount == 1 else 'Francs'
    return f'{words} {franc} CFA'
