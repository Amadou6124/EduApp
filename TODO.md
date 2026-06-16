# TODO — Dette technique découverte

## forms.py brand-blue (design)

Les constantes `_INPUT` / `_INPUT_SM` / `_CHECKBOX` dans les fichiers `forms.py`
utilisent encore `focus:ring-brand-blue focus:border-brand-blue` (et
`text-brand-blue` pour les checkbox) — alias **supprimé** lors de la refonte
design (Phase E). Les inputs rendus par ces forms ont donc perdu leur couleur de
focus.

**Fichiers à corriger** (scan `grep -rl "brand-blue\|brand-gold" apps/ --include="*.py"`) :
- `apps/accounts/team_forms.py`
- `apps/accounts/forms.py`
- `apps/payments/forms.py`
- `apps/schools/forms.py`

**Fix** : remplacer `brand-blue` par `primary-500` (ring/border) et `primary-600`
(text) dans les constantes CSS des forms.

**Priorité** : faible (cosmétique, focus ring).
**Phase** : passe dédiée après QA complète.

## Fonctionnalité manquante

### Alerte émargement dashboard
Ajouter dans `_compute_alerts` : comparer profs attendus vs `TeacherAttendance`
du jour. Apparaît si profs non émargés ce jour.

**Priorité** : moyenne.

### Réactivation élève archivé (onglet « Archivés »)
Équivalent élève de la réactivation équipe (déjà faite). Ajouter un onglet/filtre
« Archivés » dans la liste élèves (`filter=archived` → `is_active=False`) + un
bouton « Réactiver » par élève (vue `student_reactivate`, directeur). En attendant,
réactivation via superadmin/shell uniquement.

**Priorité** : moyenne.

### Carte « Évolution des inscriptions » en demi-largeur
Dashboard : quand une seule carte graphique est visible (staff voyant les élèves
mais pas les paiements, ou inversement), la grille `lg:grid-cols-2` laisse la carte
restante en demi-largeur avec un vide à droite. Rendre la carte survivante pleine
largeur via une classe conditionnelle.

**Priorité** : faible (cosmétique).

### Suppression définitive de classe
Actuellement la suppression de classe est un soft-delete (`is_active=False`) avec
réactivation auto si recréation du même nom. Pas de suppression DB définitive depuis
l'UI (les FK `PROTECT` — Note, Bulletin, enrollments — la bloqueraient de toute façon
si des données existent). À envisager seulement pour les classes vraiment vides et
sans historique.

**Priorité** : faible (rare).
