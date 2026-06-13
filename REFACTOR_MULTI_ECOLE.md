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
- [x] Membership (user, school, role, is_default)
- [x] SchoolGroup (promoteur → écoles)
- [x] StudentGuardian (parent → enfant)
- [x] StudentEnrollment (historique transferts)

### Modifications existantes
- [ ] get_school() → lit session active_school_id
- [ ] SchoolMiddleware → request.role per-école
- [ ] StaffPermission → lié à Membership
- [ ] User.role → déprécié (gardé comme cache)
- [ ] 2 décorateurs → utilisent request.role
- [ ] 5 templates → utilisent request.role

## Phases

### PHASE A — Schéma additif
Statut : ✅ Terminée
- [x] Créer Membership
- [x] Créer SchoolGroup + School.group
- [x] Créer StudentGuardian
- [x] Créer StudentEnrollment
- [x] Ajouter membership FK nullable sur StaffPermission
- [x] Migration appliquée

Migrations générées (ordre strict schools → accounts → students) :
- `schools/0012_add_school_group.py`
- `accounts/0003_add_membership_promoter_role.py`
- `students/0004_add_guardian_enrollment.py`

### PHASE B — Migration données
Statut : ✅ Terminée
- [x] RunPython : User → Membership
- [x] RunPython : StaffPermission → membership FK
- [x] RunPython : Student → StudentEnrollment
- [x] Validation données migrées

Migration : `accounts/0004_backfill_memberships_phase_b.py`
(3 RunPython idempotents, reverse=noop)
Résultat backfill : 11 Memberships · 640 Enrollments · 3/3 StaffPermissions liées

### PHASE C — Bascule logique
Statut : 🔄 En cours
- [x] get_school() → session + Membership
- [x] SchoolMiddleware → request.role
- [x] director_or_staff_required → request.role
- [x] teacher_required → request.role
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
- `dee97c4` chore: REFACTOR_MULTI_ECOLE.md - plan architecture multi-école
- `176142e` feat: multi-école Phase A - modèles + migrations additives zéro régression
- `9fe8298` feat: multi-école Phase B - backfill données existantes
- `5f782a2` feat: multi-école Phase C1 - get_school() session + get_active_role() + request.role
- _(à venir)_ feat: multi-école Phase C2 - décorateurs lisent get_active_role()
