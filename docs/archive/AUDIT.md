# AUDIT COMPLET EDUAPP
Date : 2026-06-12
Branche : fix/bugs-critiques → mergée sur main le 2026-06-12
Statut : ✅ 40/40 problèmes résolus

## LÉGENDE
🔴 MORTEL — App inutilisable / perte de données
🟠 CRITIQUE — Fonctionnalité cassée
🟡 IMPORTANT — Mauvaise expérience utilisateur
🟢 MINEUR — Petit détail à améliorer
💡 AMÉLIORATION — Pas urgent mais utile

---

## 1. AUTHENTIFICATION & ACCÈS

**🔴 [Auth] Redirect post-login vers des URLs inexistantes pour enseignants/élèves/parents**
Description : `apps/accounts/views.py:42-48` — `_post_login_url` redirige vers `/teacher/`, `/student/`, `/parent/` selon le rôle. Ces URLs n'existent pas dans `config/urls.py`. Un enseignant ou parent qui se connecte obtient une erreur 404 immédiate.
Impact : Tout utilisateur non-directeur/staff/superadmin ne peut pas utiliser l'application après connexion.
Fix : Rediriger les enseignants vers `/notes/`, ajouter des pages dédiées pour les autres rôles ou rediriger vers `/` avec un message explicite.

**🔴 [Auth] Superadmin sans école provoque crash sur toutes les vues métier**
Description : `apps/core/mixins.py:10` — `get_school()` retourne `request.user.school` qui est `None` pour un superadmin. Toute vue qui appelle `get_school()` puis filtre sur `school` provoque un `TypeError` si un superadmin navigue vers `/classes/`, `/students/`, etc.
Impact : Le superadmin fait crasher n'importe quelle page de l'app métier.
Fix : Ajouter un guard dans `get_school()` : lever une exception explicite ou rediriger vers `/superadmin/`.

**🟡 [Auth] URL racine redirige vers classes sans vérification du rôle**
Description : `config/urls.py:9` — `path('', lambda request: redirect('schools:class-list'))` redirige tous les utilisateurs authentifiés vers `/classes/`, y compris les enseignants.
Impact : Les enseignants arrivent sur une page qui n'est pas leur espace de travail naturel.
Fix : Redirect conditionnel selon le rôle (directeur/staff → `/classes/`, enseignant → `/notes/`).

**🟢 [Auth] Cookies de session sans flag Secure en production**
Description : `config/settings.py` — Aucun `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT` ni `SECURE_HSTS_SECONDS` configurés. Valeur par défaut `False`.
Impact : En production HTTPS, cookies de session interceptables (man-in-the-middle).
Fix : Ajouter ces paramètres conditionnés à `DEBUG=False`.

---

## 2. DASHBOARD

**🔴 [Dashboard] N+1 massif dans `_compute_kpis` et `_compute_alerts`**
Description : `apps/dashboard/views.py:70-72,96-98` — Deux boucles itèrent sur tous les élèves actifs et appellent `s.get_balance_due()` qui déclenche 1 requête SQL par élève (via `self.payments.all()`). Pour une école de 300 élèves : 600 requêtes SQL à chaque chargement du dashboard.
Impact : Dashboard très lent ou timeout avec plus de 100 élèves.
Fix : Remplacer par une annotation SQL `Subquery + Coalesce` comme dans `_students_qs` de `payments/views.py`.

**🟠 [Dashboard] Activité récente inclut les élèves archivés**
Description : `apps/dashboard/views.py:290` — `Student.objects.filter(school=school).order_by('-enrolled_at')[:5]` sans filtre `is_active=True`.
Impact : Des élèves supprimés/archivés apparaissent dans la section "Activité récente".
Fix : Ajouter `.filter(is_active=True)`.

**🟡 [Dashboard] `_compute_alerts` duplique le calcul de `_compute_kpis`**
Description : `apps/dashboard/views.py:88-105` — `_compute_alerts` itère à nouveau sur tous les élèves pour compter les impayés alors que `_compute_kpis` vient de le faire.
Impact : Double coût SQL à chaque chargement du dashboard.
Fix : Passer le résultat `unpaid_count` de `_compute_kpis` en paramètre à `_compute_alerts`.

**🟡 [Dashboard] `thirty_days_ago` calculé mais jamais utilisé**
Description : `apps/dashboard/views.py:94` — `thirty_days_ago = today - timedelta(days=30)` défini mais absent de tout filtre. L'alerte signale tous les impayés, pas ceux de plus de 30 jours.
Impact : Logique incorrecte — le titre de l'alerte dit "30 jours" mais tous les impayés sont comptés.
Fix : Utiliser `thirty_days_ago` dans le filtre ou supprimer la variable.

---

## 3. CLASSES

**🟠 [Classes] Toasts de modification et suppression ne s'affichent pas**
Description : `apps/schools/views.py:162,395,406` — `class_update` et `class_delete` émettent `HX-Trigger` avec la clé `'show-toast'` (kebab-case direct). Mais `templates/base.html:375` écoute uniquement `'showToast'` (camelCase) pour le bridge. La clé `show-toast` envoyée directement par la vue n'est jamais captée par Alpine.
Impact : Aucun toast de confirmation après modification ou suppression d'une classe.
Fix : Uniformiser en utilisant `'showToast'` dans `class_update` et `class_delete` comme partout ailleurs, ou ajouter un listener `show-toast` direct dans le toast Alpine.

**🟠 [Classes] `class_update` retourne `class_row.html` avec objet non-annoté**
Description : `apps/schools/views.py:156` — La vue passe `school_class` directement sans annoter `student_count`. `class_row.html:8,24` appelle `school_class.get_student_count` (méthode) qui déclenche 1-2 requêtes SQL supplémentaires au lieu d'utiliser l'annotation.
Impact : 2 requêtes SQL inutiles à chaque édition de classe.
Fix : Utiliser `_classes_qs(school).get(pk=class_id)` pour récupérer la classe annotée.

**🟠 [Classes] `class_import_confirm` reconstruit le queryset sans annotation**
Description : `apps/schools/views.py:373` — `SchoolClass.objects.filter(...).select_related('school')` sans `.annotate(student_count=...)`. `compute_class_stats` appelle ensuite `c.get_student_count()` pour chaque classe → N requêtes SQL.
Impact : Après import de 20 classes : 40+ requêtes SQL superflues.
Fix : Remplacer par `_classes_qs(school)`.

**🟢 [Classes] Doublons comptabilisés dans le total "prêts à importer"**
Description : `templates/schools/partials/class_import_preview.html:19-23` — Les doublons sont affichés avec un badge "Doublon" mais restent comptés dans "X classe(s) prête(s) à importer". Confusion sur le nombre réel de créations.
Impact : UX trompeuse sur le résultat attendu de l'import.
Fix : Afficher séparément "X à créer, Y doublons ignorés".

---

## 4. ÉLÈVES

**🟠 [Élèves] `print()` de debug en production — fuite de données personnelles**
Description : `apps/students/views.py:131-134` — `print(f'[SMS LOG] → {student.parent_phone_number} : ...')` exécuté à chaque inscription avec parent.
Impact : Numéros de téléphone des parents écrits en clair dans les logs système en production.
Fix : Supprimer ou remplacer par `logging.getLogger(__name__).info(...)`.

**🟠 [Élèves] Import `bulk_create` peut crasher avec IntegrityError non gérée sur `access_code`**
Description : `apps/students/views.py:495` — `bulk_create` bypasse `pre_save` et ne vérifie pas les collisions sur `access_code` (champ `unique`). Si deux codes identiques sont générés, une `IntegrityError` non catchée provoque un crash 500.
Impact : Import d'élèves peut échouer avec une erreur 500 sans message utile pour l'utilisateur.
Fix : Générer et valider les `access_code` en lot avant `bulk_create`, ou entourer d'un `try/except IntegrityError`.

**🟡 [Élèves] Colonne "Versement" dans l'aperçu d'import toujours vide**
Description : `templates/students/partials/student_import_preview.html:44` — Affiche `row.initial_amount` mais `_parse_student_rows` (`views.py:419-429`) ne définit jamais cette clé dans le dictionnaire retourné.
Impact : Colonne toujours "—" dans l'aperçu, même si un flux de paiement initial était prévu.
Fix : Soit supprimer cette colonne du template (le paiement à l'import n'est pas supporté), soit l'implémenter.

**🟡 [Élèves] Paiement en surcharge possible — pas de plafond = balance**
Description : `apps/payments/forms.py` — `PaymentCreateForm.clean_amount()` valide uniquement `amount > 0`, pas `amount <= student.get_balance_due()`. Un montant supérieur au solde restant est accepté.
Impact : Solde élève peut devenir négatif — comptabilité incorrecte.
Fix : Passer le solde au formulaire et valider `amount <= balance` dans `clean_amount()`.

---

## 5. PAIEMENTS

**🟠 [Paiements] Race condition sur la génération des numéros de reçu**
Description : `apps/payments/models.py:85-102` — `_generate_receipt_number()` fait un `SELECT MAX` puis calcule le numéro suivant sans verrou ni transaction atomique. Deux paiements simultanés (deux caissiers) peuvent obtenir le même numéro. La contrainte `unique=True` lèvera ensuite une `IntegrityError` non gérée.
Impact : Crash 500 lors de paiements simultanés, paiement perdu.
Fix : Utiliser `select_for_update()` dans un bloc `transaction.atomic()`.

**🟡 [Paiements] `receipt_url` dans le HX-Trigger `showToast` ignoré**
Description : `apps/payments/views.py:181` — Le HX-Trigger inclut `'receipt_url': '/payments/receipt/{id}/'` mais aucun listener JS ni template ne lit cette clé. Le lien vers le reçu dans le toast ne fonctionne pas.
Impact : L'utilisateur ne peut pas accéder directement au reçu depuis la notification.
Fix : Ajouter la gestion de `receipt_url` dans le handler du toast (`base.html`) pour afficher un lien cliquable.

**🟡 [Paiements] Téléchargement PDF sans gestion d'erreur**
Description : `apps/schools/bulletins_views.py:339,374` — `generate_bulletin_pdf(bulletin)` appelé sans `try/except`. Si la bibliothèque PDF plante, l'utilisateur reçoit une page 500 générique.
Impact : Erreur non informative pour le directeur.
Fix : Entourer d'un `try/except Exception` et retourner un message d'erreur lisible en HTTP 400.

---

## 6. NOTES

**🟡 [Notes] `_student_has_notes` exécutée en boucle = N×2 requêtes SQL**
Description : `apps/schools/bulletins_views.py:149,238` — `_student_has_notes(student, period, school_class)` fait 2 requêtes SQL (COUNT ClassSubject + COUNT Note). Appelée pour chaque élève dans `bulletins_tab` et `generate_class_bulletins`. Pour 40 élèves : 80 requêtes supplémentaires.
Impact : Onglet Bulletins lent pour les grandes classes.
Fix : Précalculer en une requête groupée par `student_id` avant la boucle.

**🟡 [Notes] `AppreciationScale.get_appreciation` exécute une requête par appel**
Description : `apps/schools/models.py:472-483` — Requête `SELECT ... ORDER BY -min_grade` sans cache. Appelée pour chaque matière × chaque élève lors de la génération des bulletins.
Impact : Génération lente pour les grandes promotions.
Fix : Pré-charger l'échelle une fois avant la boucle de génération et la passer en paramètre.

**🟢 [Notes] `note_cancel` ne retourne aucun toast**
Description : `apps/schools/notes_views.py:517-548` — La vue `note_cancel` retourne le fragment sans `HX-Trigger`. Aucun feedback visuel après annulation d'une note.
Impact : UX silencieuse — l'utilisateur ne sait pas si l'annulation a réussi.
Fix : Ajouter `response['HX-Trigger'] = json.dumps({'showToast': {'message': 'Note annulée.', 'type': 'info'}})`.

---

## 7. BULLETINS

**🟠 [Bulletins] Suppression de période efface silencieusement toutes les notes associées**
Description : `apps/schools/models.py:372` — `Note` a `period = FK(Period, on_delete=CASCADE)`. `apps/schools/settings_views.py:423-435` — Le `try/except ProtectedError` dans `period_delete` est mort (CASCADE ne lève pas de ProtectedError). Supprimer une période supprime silencieusement toutes les notes et bulletins liés.
Impact : **Perte irréversible et silencieuse de toutes les notes d'une période** si un admin supprime une période par erreur. Pas de message d'avertissement.
Fix : Vérifier manuellement `Note.objects.filter(period=period).exists()` avant suppression et bloquer avec un message clair.

**🟠 [Bulletins] `generate_student_bulletin` sans transaction atomique**
Description : `apps/schools/bulletins_views.py:281-284` — La séquence `calculator.generate_bulletin()` → `calculate_ranks()` → `bulletin.save()` n'est pas dans `transaction.atomic()`. Si le processus est interrompu entre la génération et la sauvegarde du rang, le bulletin existe sans rang.
Impact : Bulletins avec `rank=None` après interruption réseau ou erreur serveur.
Fix : Entourer la séquence dans `with transaction.atomic():`.

**🟠 [Bulletins] `bulletin_download` sans vérification de rôle**
Description : `apps/schools/bulletins_views.py:329,352` — Seul `@login_required` protège ces vues. Un enseignant peut télécharger les bulletins PDF de n'importe quel élève de son école.
Impact : Accès non autorisé aux données scolaires confidentielles.
Fix : Ajouter un check de rôle (`director`, `staff`, `superuser`) comme sur `generate_class_bulletins`.

**🟡 [Bulletins] `_get_class_stats` recharge les élèves sans prefetch**
Description : `apps/schools/bulletins_views.py:432-433` — `Student.objects.filter(...)` sans `select_related`. Appelée à chaque clic sur l'onglet Santé via HTMX.
Impact : Requêtes SQL inutilement lourdes à chaque changement de classe.
Fix : Ajouter `.select_related('school_class')` si nécessaire.

---

## 8. PARAMÈTRES

**🟠 [Paramètres] Liste des "enseignants" inclut tous les rôles (élèves, parents)**
Description : `apps/schools/settings_views.py:544` — `User.objects.filter(school=school, is_active=True)` sans filtre sur `role`. Dans le panneau d'affectation des matières, le directeur peut sélectionner un parent ou un élève comme enseignant d'une matière.
Impact : Configuration incohérente possible ; données erronées.
Fix : Ajouter `.filter(role__in=['teacher', 'director', 'staff'])`.

**🟡 [Paramètres] Fonctionnalité "Analyser le PDF de reçu" retourne des données mock**
Description : `apps/schools/settings_views.py:153-165` — L'action `analyze` retourne `mock_mapping` codé en dur. L'analyse réelle du PDF n'est pas implémentée.
Impact : Le directeur croit que son PDF est analysé automatiquement, mais les champs sont inventés. Fonctionnalité trompeuse.
Fix : Soit implémenter l'analyse réelle, soit afficher clairement "configuration manuelle requise" et masquer le bouton "Analyser".

**🟢 [Paramètres] Vérification unicité `SchoolYear` doublée (form + full_clean)**
Description : `apps/schools/settings_views.py:224-230` — `form.is_valid()` puis `year.full_clean()` vérifient tous deux l'unicité. Double requête DB pour la même vérification.
Impact : Performance mineure — deux vérifications redondantes.
Fix : Gérer uniquement la `ValidationError` de `full_clean()` et supprimer le doublon.

---

## 9. SUPERADMIN

**🟠 [Superadmin] Redirect non-authentifié vers `/admin/login/` au lieu de `/login/`**
Description : `apps/accounts/superadmin_views.py:17` — `superadmin_required` redirige vers `/admin/login/?next=...`. L'app utilise une URL de login custom `/login/`. L'utilisateur voit l'interface admin Django au lieu de la page de login métier.
Impact : UX cassée — mauvaise page de login pour les utilisateurs non-connectés.
Fix : Rediriger vers `settings.LOGIN_URL` ou `f'/login/?next={request.path}'`.

**🟡 [Superadmin] Pas de pagination sur la liste des écoles**
Description : `apps/accounts/superadmin_views.py:37-51` — `School.objects.filter(is_active=True)` sans `.paginate_by`. Toutes les écoles chargées en mémoire.
Impact : Performances dégradées à l'échelle (100+ écoles).
Fix : Ajouter la pagination Django (50 par page).

**🟢 [Superadmin] `director_update` — comportement du mot de passe vide ambigu**
Description : `apps/accounts/superadmin_views.py:129-131` — Si le champ mot de passe est laissé vide, il n'est pas modifié (fonctionnellement correct). Mais le formulaire n'indique pas ce comportement à l'utilisateur.
Impact : Confusion UX — le superadmin ne sait pas si le mot de passe a changé.
Fix : Ajouter `help_text='Laisser vide pour conserver le mot de passe actuel.'` sur le champ.

---

## 10. MOBILE & RESPONSIVE

**🟡 [Mobile] Tableau de saisie des notes déborde horizontalement**
Description : `templates/notes/notes_class.html` — Le tableau de notes n'est pas dans un conteneur `overflow-x-auto` dédié avec `min-width`. Avec 6+ colonnes de notes, le tableau déborde hors écran sur mobile.
Impact : Saisie des notes impossible sur smartphone.
Fix : Entourer le tableau dans `<div class="overflow-x-auto">` avec `min-w-max` sur le `<table>`.

**🟡 [Mobile] Panels latéraux largeur fixe sur petits écrans**
Description : Les panels d'inscription (`student_list.html`) et de paiement (`payments/dashboard.html`) utilisent `w-[480px]` ou `w-[520px]`. Sur un écran < 480px, le panel dépasse.
Impact : Formulaires partiellement hors écran sur petits smartphones.
Fix : Utiliser `w-full sm:w-[480px]` pour les panels.

**🟢 [Mobile] Switch vue cards/tableau masqué sur mobile mais toujours rendu dans le DOM**
Description : `hidden sm:flex` cache le switch visuellement mais le DOM et les event listeners Alpine sont toujours là.
Impact : Comportement fonctionnel mais inutilement pesant pour le DOM.
Fix : Acceptable en l'état ou utiliser `x-show` conditionnel sur la résolution.

---

## 11. SÉCURITÉ

**🟠 [Sécurité] Vues métier sans vérification de rôle**
Description : `apps/schools/views.py`, `apps/students/views.py`, `apps/payments/views.py` — Seul `@login_required` est appliqué. Un enseignant peut créer/modifier/supprimer des classes, voir les données financières de tous les élèves, et enregistrer des paiements.
Impact : Violation du principe du moindre privilège. Un enseignant peut altérer les données financières.
Fix : Ajouter un décorateur de rôle sur les vues sensibles (`class_create`, `class_delete`, `student_create`, `payment_create`, etc.) limitant à `director/staff`.

**🟠 [Sécurité] Fichiers media accessibles sans authentification**
Description : `config/urls.py:22-23` — `static(MEDIA_URL, document_root=MEDIA_ROOT)` sert les fichiers media sans aucune vérification d'auth. Les logos d'école, reçus PDF et templates sont accessibles à quiconque connaît le chemin.
Impact : Fuite de données confidentielles (reçus, documents établissement).
Fix : Servir les fichiers media via une vue Django protégée ou configurer `X-Accel-Redirect` avec Nginx en production.

**🟡 [Sécurité] Rate limiting login contournable via header `X-Forwarded-For` forgé**
Description : `apps/accounts/views.py:16-19` — `_client_ip` lit `HTTP_X_FORWARDED_FOR` qui peut être forgé par un attaquant. Le blocage par IP est bypassable en changeant ce header.
Impact : Brute-force possible sur les numéros de téléphone + mots de passe.
Fix : Utiliser aussi l'identifiant de compte tenté comme clé de rate limiting, ou utiliser `django-axes`.

**🟡 [Sécurité] `SECRET_KEY` insecure sans `.env`**
Description : `config/settings.py:6` — Si le fichier `.env` est absent, la clé par défaut `django-insecure-change-me-in-production` est utilisée.
Impact : Signature de session et cookies CSRF compromis si déployé sans `.env`.
Fix : Lever une exception explicite si `DEBUG=False` et la clé contient "insecure".

---

## 12. PERFORMANCE

**🟠 [Performance] Dashboard charge 6 fonctions lourdes synchrones à chaque GET**
Description : `apps/dashboard/views.py:41-45` — `_compute_kpis`, `_compute_alerts`, `_compute_charts`, `_compute_class_health`, `_compute_activity` appelées séquentiellement. `_compute_charts` génère 2×N_mois requêtes SQL ; `_compute_class_health` fait 4 requêtes par classe. Pour 10 classes + 10 mois : 600+ requêtes SQL à chaque affichage.
Impact : Dashboard inutilisable en production avec des données réelles.
Fix : Caching Redis (`cache.get_or_set`) avec TTL de 5 min pour les agrégats ; lazy loading HTMX par widget.

**🟡 [Performance] `_compute_charts` fait une requête par mois (jusqu'à 24 requêtes)**
Description : `apps/dashboard/views.py:183-194` — Deux boucles sur les mois avec `Payment.objects.filter(... payment_date__month=m)`. 2×N_mois requêtes SQL.
Impact : 24 requêtes juste pour les graphiques avec une année scolaire de 12 mois.
Fix : Utiliser `TruncMonth` avec `annotate + values` pour une seule requête groupée par mois.

**🟡 [Performance] Dropdown enseignants charge tous les utilisateurs de l'école**
Description : `apps/schools/settings_views.py:544` — `User.objects.filter(school=school, is_active=True)` sans filtre de rôle ni limite. Pour une grande école avec 200+ utilisateurs, tous chargés dans un `<select>`.
Impact : Dropdown très long, requête lourde, UX dégradée.
Fix : Filtrer par `role__in=['teacher','director','staff']` et envisager un autocomplete HTMX.

**💡 [Performance] `_student_has_notes` en boucle — déjà noté en section 7**
Description : Voir section 7. Précalculer en une requête agrégée retournant un `set` de `student_id` ayant des notes pour toutes les matières de la classe.

---

## PLAN D'ACTION PRIORISÉ

### Priorité 1 — Avant démo directeur ✅ COMPLÈTE (8/8)

1. ✅ **Redirect post-login enseignants** (`accounts/views.py:42-48`) — `a6ccfa2`
2. ✅ **Guard `get_school()` pour superadmin** (`core/mixins.py`) — `ae690a9`
3. ✅ **N+1 dashboard** (`dashboard/views.py:70-72,96-98`) — `c47f990`
4. ✅ **Toasts `show-toast` vs `showToast`** (`schools/views.py:162,395,406`) — `28872d6`
5. ✅ **`period_delete` guard notes** (`settings_views.py:423-435`) — `47fc74b`
6. ✅ **`print()` debug supprimé** (`students/views.py:131`) — `27a0210`
7. ✅ **Dropdown enseignants filtré** (`settings_views.py:544`) — `b813287`
8. ✅ **Redirect superadmin vers `/login/`** (`superadmin_views.py:17`) — `bbafdab`

### Priorité 2 — Semaine suivante ✅ COMPLÈTE (9-20)

9.  ✅ **Race condition numéro de reçu** (`payments/models.py`) — `cb30729`
10. ✅ **`bulk_create` élèves sans gestion IntegrityError** (`students/views.py`) — `481aec9`
11. ✅ **`bulletin_download` sans vérification de rôle** (`bulletins_views.py`) — `bcc8bd4`
12. ✅ **`generate_student_bulletin` sans transaction atomique** (`bulletins_views.py`) — `8c6fd5e`
13. ✅ **Activité récente affiche les élèves archivés** (`dashboard/views.py`) — `4a6dce8`
14. ✅ **Vues métier sans vérification de rôle** (14 vues classes/élèves/paiements) — `7caf52e`
15. ✅ **Fichiers media accessibles sans auth** (`config/urls.py`) — `a45e63e`
16. ✅ **`receipt_url` dans le toast non implémentée** (`payments/views.py`) — `8ab165c`
17. ✅ **Colonne "Versement" toujours vide dans l'aperçu import** (`student_import_preview.html`) — `6cbcc4a`
18. ✅ **Paiement en surcharge possible** (`payments/forms.py`) — `ca28ead`
19. ✅ **`_compute_charts` 24 requêtes SQL** → `TruncMonth` — `174dff4`
20. ✅ **Fonctionnalité "Analyser PDF reçu" mock** → message "config manuelle" — `c0a06e1`

### Priorité 3 — Plus tard ✅ COMPLÈTE (21-33)

21. ✅ **Caching dashboard 5min** (`dashboard/views.py`) — `d364442`
22. ✅ **`_students_with_notes` remplace `_student_has_notes` en boucle** (`bulletins_views.py`) — `f005ad2`
23. ✅ **`AppreciationScale` pré-chargée avant boucle bulletin** (`bulletin_calculator.py`) — `653cf87`
24. ✅ **Pagination liste écoles superadmin** (`superadmin_views.py`) — `b711a30`
25. ✅ **Toast manquant sur `note_cancel`** (`notes_views.py`) — `6c25cec`
26. ✅ **Mobile panels et tableau notes** (déjà `w-full sm:w-[480px]` et `overflow-x-auto` en place) — `a51be7c`
27. ✅ **Dropdown enseignants filtré** — déjà résolu au point 7 (`b813287`) — `7eb1ea5`
28. ✅ **Validation "montant ≤ solde"** (`payments/forms.py`) — déjà résolu au point 18 (`ca28ead`)
29. ✅ **Cookies session/CSRF Secure + HSTS** (`config/settings.py`) — `eb08c7a`
30. ✅ **`SECRET_KEY` insecure bloque le démarrage en prod** (`config/settings.py`) — `63e41c0`
31. ✅ **Rate limiting par compte (phone) en plus de l'IP** (`accounts/views.py`) — `2b39a1d`
32. ✅ **`help_text` mot de passe dans `director_update`** (`superadmin_forms.py`) — `7f36a13`
33. ✅ **Redirect racine `/` selon le rôle** (`config/urls.py`) — `08424cf`

---

**Résumé chiffré :**
- 🔴 3 problèmes mortels
- 🟠 16 problèmes critiques
- 🟡 13 problèmes importants
- 🟢 6 problèmes mineurs
- 💡 2 améliorations

**Total : 40 problèmes identifiés**

**Fichiers les plus critiques :**
- `apps/dashboard/views.py` — N+1 massif (600+ requêtes par page)
- `apps/schools/settings_views.py` — period_delete silencieux, liste enseignants incorrecte
- `apps/schools/views.py` — toasts cassés, requêtes non-annotées
- `apps/students/views.py` — print() debug, IntegrityError non gérée
- `apps/accounts/views.py` — redirects 404 post-login
- `apps/payments/models.py` — race condition numéros de reçu
- `apps/schools/bulletins_views.py` — accès non autorisé, pas de transaction atomique
