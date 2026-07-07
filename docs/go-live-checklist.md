# Checklist go-live — EduApp

Tout ce qu'il reste à faire pour passer d'une **démo** à un **vrai lancement**, **dans l'ordre
d'exécution**. On coche de haut en bas. Voir aussi [roadmap-post-demo.md](roadmap-post-demo.md)
pour le détail des évolutions produit.

Principe de l'ordre :
- **A (1→5)** : impossible d'ouvrir à qui que ce soit sans ça.
- **B (6→8)** : ne pas ouvrir sans confiance (isolation, tests, base propre).
- **C (9→11)** : le pilote réel.
- **D (12→14)** : ce qu'on corrige *pendant* le pilote (ciblage frais tôt, passage d'année avant juin).
- **E (15→16)** : confort et expansion, après.

---

## 🅰️ Rendre l'app lançable (technique) — AVANT tout utilisateur réel

- [ ] **1. Hébergement réel + base Postgres managée** (Render / VPS / PythonAnywhere). Fini laptop + ngrok.
- [ ] **2. Config production** : `DEBUG=False`, vrai `SECRET_KEY`, domaine réel, `ALLOWED_HOSTS` +
      `CSRF_TRUSTED_ORIGINS`, HTTPS. *(HSTS / cookies sécurisés s'activent déjà quand `DEBUG=False`.)*
- [ ] **3. Sauvegardes automatiques de la base** + **tester une restauration**. Non négociable.
- [ ] **4. Monitoring d'erreurs** (Sentry ou équivalent) → être alerté d'un 500 avant l'appel du directeur.
- [ ] **5. Environnement de staging** (copie de prod) pour tester avant de déployer.

## 🅱️ Fiabiliser avant d'ouvrir

- [ ] **6. Audit d'isolation multi-écoles** : un directeur A ne voit JAMAIS les données de l'école B
      (vérifier `SchoolMiddleware` + tous les querysets scopés par école).
- [ ] **7. Tests automatisés sur les chemins critiques** : paiements/encaissement, génération des frais,
      notes → bulletins. *(Aujourd'hui : zéro test sur ces apps.)*
- [ ] **8. Base propre** : ouvrir la prod sur une base **vierge** (démo gardée en local). Le code a
      été vérifié : rien ne fabrique de fausses données tout seul. Recette : [ouvrir-prod-vierge.md](ouvrir-prod-vierge.md).

## 🅲️ Pilote contrôlé (1-2 vraies écoles)

- [ ] **9. Créer les vrais comptes** (école + directeur, **vrais mots de passe** — plus de `test123`).
- [ ] **10. Onboarding** via le guide : année → **classes** → périodes → frais → matières → matières×classes
      → enseignants → élèves.
- [ ] **11. Observer + corriger vite** (support proche les premières semaines).

## 🅳️ Corriger les manques pendant le pilote (dans l'ordre où ça mord)

- [ ] **12. Ciblage des frais par niveau** 🔴 — mord dès l'onboarding si plusieurs cycles
      (inscription préscolaire ≠ fondamental). Plan écrit dans la roadmap.
- [ ] **13. Polish rapides** : nombre de tranches libre (2/4/6), couleur/abréviation des matières,
      découvrabilité de la rémunération prof.
- [ ] **14. Passage d'année** 🔴 — gros chantier, mais ne mord qu'à la **fin de l'année scolaire**
      → à finir **avant** la première bascule (juin).

## 🅴️ Évolutions produit (après pilote validé)

- [ ] **15. Emploi du temps + fiche enseignant** 🟠 (planning hebdo + vue unique des heures d'un prof).
- [ ] **16. (Optionnel) Supérieur / LMD** — seulement si tu vises l'université. Sinon on reste **K-12**.

---

## ✅ Déjà réglé (session « périodes par cycle » — dans `main`)

- Périodes par cycle (compositions/trimestres) + surcharge par classe.
- Auto-provisionnement des gabarits de tranches + bouton « frais d'exemple » propre.
- Écran années peaufiné (archivage rassurant, suppression réservée aux années vides).
- Fix crash dashboard (dates du flux d'activité).
- Wording « Tranches → Échéances » (onglet En retard).
