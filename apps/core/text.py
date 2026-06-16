"""Utilitaires texte partagés (multi-app)."""
import unicodedata


def norm_name(s):
    """Normalise une chaîne pour comparaison/recherche : sans accents, casefold, strippée.

    Ex. : norm_name('Moïsé') == norm_name('moise') → True.
    Utilisé pour la réactivation de classes et la recherche d'élèves
    (insensible casse + accents, sans extension PostgreSQL).
    """
    return unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().casefold().strip()
