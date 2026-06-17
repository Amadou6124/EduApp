## Tâches futures planifiées

### Lucide : migration 1.20.0 → 0.577.x (branche dédiée)
- Contexte : l'app charge Lucide legacy 1.20.0 (2021, 408 Ko).
  La lib moderne est en 0.x (dernière : 0.577.0, maintenue).
- Risque : noms d'icônes changés entre 1.20.0 et 0.577.x
  → audit obligatoire avant migration.
- Étapes :
  1. grep -rohE 'data-lucide="[^"]+"' templates/ | sort -u
     (lister tous les noms utilisés)
  2. Vérifier chaque nom sur https://lucide.dev/icons/
  3. Mettre à jour vendor_assets.py (1.20.0 → 0.577.x)
  4. Remplacer les noms obsolètes dans les templates
  5. Test visuel complet page par page (chargement + après swap HTMX)
- Branche suggérée : chore/lucide-upgrade

### Chart.js : déjà self-hosté (4.4.1) ✅

---

## Scroll horizontal résiduel (Safari iOS)
- HTML/BODY débordent de 136px (scrollWidth 536 dans viewport 400px)
- Suspect : enfant direct de `div.flex.min-h-screen` dans base.html
- Script de détection déjà prêt (console Safari Web Inspector)
- Branche suggérée : fix/mobile-scroll

## Erreurs Alpine console
- `this.classes.find is not a function` (page inscription élève ?)
- `lucide.min.js.map` 404 (source map manquante, sans impact fonctionnel)
- Branche suggérée : fix/alpine-errors
