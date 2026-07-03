"""Attribution automatique et déterministe d'une couleur à une matière.

Scalable primaire → université (5 à 30+ matières) : on ne peint JAMAIS une matière
à la main, et le coral (accent de marque) est EXCLU (réservé aux actions).

DEUX stratégies :
 • subject_hue_at(index)  ← PRÉFÉRÉE. Couleur = position de la matière dans la
   liste de l'élève (ou ClassSubject.order). Garantit que les matières qu'un
   élève voit sont TOUTES distinctes tant qu'il y en a ≤ 8 ; au-delà, ça cycle.
   Stable pour une (classe, matière). C'est ce que voit l'élève au quotidien.
 • subject_hue(name)      ← repli, quand aucun index stable n'est disponible.
   Déterministe (md5, pas hash() salé) MAIS peut faire des collisions (deux
   matières de la même classe peuvent tomber sur la même teinte).

L'identité réelle d'une matière = nom + icône + couleur (jamais la couleur seule).
"""
import hashlib

# 8 teintes de matière — SANS coral (l'accent de marque reste aux actions).
SUBJECT_HUES = ('violet', 'sky', 'mint', 'amber', 'teal', 'pink', 'indigo', 'lime')


def subject_hue_at(index: int) -> str:
    """Teinte par POSITION (0-based) dans la liste de matières. Distinct garanti
    pour les 8 premières, puis cycle. Déterministe et stable."""
    return SUBJECT_HUES[index % len(SUBJECT_HUES)]


def subject_hue(name: str) -> str:
    """Repli par nom (md5 déterministe → index). Peut collisionner ; à n'utiliser
    que sans position stable disponible."""
    key = (name or '').strip().lower()
    if not key:
        return SUBJECT_HUES[0]
    digest = int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)
    return SUBJECT_HUES[digest % len(SUBJECT_HUES)]
