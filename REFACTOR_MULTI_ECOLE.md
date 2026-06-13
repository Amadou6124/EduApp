# Refactorisation Multi-École EduApp

## Objectif
Permettre à un utilisateur d'appartenir
à plusieurs écoles avec des rôles différents.

## Cas d'usage validés
1. Prof dans plusieurs écoles → même compte
2. Parent avec enfants dans écoles différentes
3. Promoteur propriétaire de plusieurs écoles
4. Transfert élève avec historique préservé

## Architecture décidée

### Nouveaux modèles
- [ ] Membership (user, school, role, is_default)
- [ ] SchoolGroup (promoteur → écoles)
- [ ] StudentGuardian (parent → enfant)
- [ ] StudentEnrollment (historique transferts)

### Modifications existantes
- [ ] get_school() → lit session active_school_id
- [ ] SchoolMiddleware → request.role per-école
- [ ] StaffPermission → lié à Membership
- [ ] User.role → déprécié (gardé comme cache)
- [ ] 2 décorateurs → utilisent request.role
- [ ] 5 templates → utilisent request.role

## Phases

### PHASE A — Schéma additif
Statut : 🔄 En cours
- [ ] Créer Membership
- [ ] Créer SchoolGroup + School.group
- [ ] Créer StudentGuardian
- [ ] Créer StudentEnrollment
- [ ] Ajouter membership FK nullable sur StaffPermission
- [ ] Migration appliquée

### PHASE B — Migration données
Statut : ⏳ En attente Phase A
- [ ] RunPython : User → Membership
- [ ] RunPython : StaffPermission → membership FK
- [ ] RunPython : Student → StudentEnrollment
- [ ] Validation données migrées

### PHASE C — Bascule logique
Statut : ⏳ En attente Phase B
- [ ] get_school() → session + Membership
- [ ] SchoolMiddleware → request.role
- [ ] director_or_staff_required → request.role
- [ ] teacher_required → request.role
- [ ] 5 templates → request.role
- [ ] Switch école (/switch-school/<id>/)
- [ ] UI switch dans header
- [ ] Login redirect multi-école

### PHASE D — Fonctionnalités multi-école
Statut : ⏳ En attente Phase C
- [ ] Dashboard promoteur consolidé
- [ ] Portail parent multi-école
- [ ] Transfert élève entre écoles
- [ ] StudentGuardian interface

## Risques identifiés
🔴 R1 — role per-école (5 templates + 2 décorateurs)
🟠 R2 — StaffPermission cardinalité
🟠 R4 — Session fixation
🟠 R5 — Isolation au transfert
🟠 R7 — Promoteur vs superadmin
🟠 R8 — Login redirect ambigu
🔴 R9 — StudentGuardian prérequis portail parent

## Décisions prises
- Migration additive (jamais big-bang)
- User.school conservé 1 release comme fallback
- Promoteur via SchoolGroup.owner + rôle 'promoter'
- Historique élève via StudentEnrollment
- get_school() cache sur request._active_school

## Tests obligatoires avant merge
- [ ] Prof mono-école : aucune régression
- [ ] Prof multi-école : switch fonctionne
- [ ] Parent multi-enfants : switch fonctionne
- [ ] Promoteur : voit toutes ses écoles
- [ ] Isolation : école A ne voit pas données école B
- [ ] Transfert : historique préservé
- [ ] Révocation accès : prise en compte immédiate

## Commits
(mis à jour à chaque commit)
