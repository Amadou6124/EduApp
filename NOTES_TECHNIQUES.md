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

## Labels de groupe HTMX orphelins (notifications)
- Quand le dernier item d'un groupe est supprimé via HTMX delete,
  le label groupe reste visible (rendu serveur, HTMX ne le cible pas)
- Solution propre : réponse HTMX OOB depuis notification_delete view
- Branche suggérée : fix/notif-group-labels
- Priorité : basse (comportement identique à WhatsApp)

---

## Demande de RDV parent → directeur
- Modèle MeetingRequest à créer (school, guardian, student,
  message, requested_date, status, admin_note)
- Vue parent : soumettre une demande
- Vue admin : gérer la liste (accepter/refuser/noter)
- Notification auto au directeur à la soumission
- Branche suggérée : feature/parent-rdv
- Priorité : haute

## Page "Toutes mes observations" — portail enseignant
- Contexte : l'enseignant ne peut voir que ses 5 dernières
  observations sur le dashboard. Pour retrouver une observation
  ancienne, il doit naviguer élève par élève.
- Ce qu'on veut : page /teacher/observations/ listant toutes
  les observations de l'enseignant connecté avec filtres :
  par type (behaviour/academic/health/other)
  par statut (lu par directeur / en attente / partagé parent)
  par élève (recherche)
- Modèle : StudentObservation.objects.filter(teacher=request.user)
  .select_related('student', 'student__school_class')
  .order_by('-created_at')
- Ajouter un lien "Voir toutes" sur le dashboard enseignant
  (section "Mes observations récentes")
- Branche suggérée : feature/teacher-observations
- Priorité : haute

## Justification d'absence par le parent
- Modèle AbsenceJustification à créer (attendance OneToOne,
  guardian, reason, attachment, status)
- Vue parent : soumettre depuis la page Absences
- Vue admin : valider ou refuser avec note
- Branche suggérée : feature/parent-justification
- Priorité : moyenne
