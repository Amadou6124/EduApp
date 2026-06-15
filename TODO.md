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
