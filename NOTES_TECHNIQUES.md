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
