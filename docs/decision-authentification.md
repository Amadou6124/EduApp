# Décision — Authentification élève / parent (Chantier B)

> **Statut : analysé, pas encore construit.** Ce document fige la direction retenue
> après recherche terrain (Mali) + confrontation Gemini/ChatGPT. À implémenter comme
> son propre chantier, **plus tard**. Il ne bloque pas le Chantier A (dossier d'inscription).

## Le principe fondateur : identité ≠ authentification

Ne jamais confondre **qui est l'élève** (identité administrative) et **comment il se connecte**
(authentification). Ce sont deux couches séparées.

| Couche | Rôle | Secret ? |
|---|---|---|
| Clé primaire Django (déjà là) | identifiant interne immuable | invisible |
| **Matricule** | identité administrative, imprimée (bulletin, listes) | **public — jamais un login** |
| **Code de connexion** | ouvrir une session | semi-secret |
| Mot de passe / OTP | authentifier | secret |

**Conséquence clé :** le matricule étant public, il ne doit **jamais** servir d'identifiant de
connexion. La sécurité vit dans le secret (code + mot de passe / OTP), pas dans l'identifiant.

## Cible par population

Élève et parent sont deux populations différentes → deux logiques différentes.

| Utilisateur | Connexion cible | Pourquoi |
|---|---|---|
| **Élève maternelle / début fondamental** | **Accès via le compte du parent** (pas d'identifiant enfant) | Très jeunes, pas de téléphone. Supprime tout secret à gérer côté enfant. |
| **Élève fondamental autonome** | **Code de connexion + nom de famille** (+ mot de passe optionnel selon l'école) | Simple, marche sans téléphone, sur poste partagé à l'école. C'est déjà notre système actuel. |
| **Élève collège / lycée** | **Code + nom + mot de passe** | Plus autonome, mérite un vrai secret. |
| **Parent** | Phase 1 : téléphone + mot de passe, **changement forcé à la 1ʳᵉ connexion**. Phase 2 (avec SMS) : **téléphone + OTP** puis mot de passe. | Les parents ont un téléphone. Évite la corvée de distribution de mots de passe. |
| **Enseignant / personnel / directeur / promoteur** | Téléphone + mot de passe (OTP en option pour actions sensibles) | Comptes privilégiés. |

## Ce qu'on NE fait PAS (et pourquoi)

**Pas de modèle `Person` / UUID global qui suit l'élève entre écoles** (proposé par ChatGPT).
Élégant, mais :
1. **Casse l'isolation multi-tenant** (pilier de sécurité, 12 tests) : deux écoles concurrentes
   ne partagent aucune base ; École B ne doit pas voir l'existence d'un élève chez École A.
2. **Bénéfice irréalisable aujourd'hui** : pour que l'identité suive un transfert, il faut un
   **registre central** — c'est précisément le matricule national, pas encore universel.

→ À la place : garder `Student` rattaché à **une** école ; un transfert = ré-inscription chez la
nouvelle école (comme la réalité papier : bulletin + certificat de radiation apportés à la main).

## Le crochet pour l'avenir

Ajouter un champ **`matricule_national` (nullable, vide aujourd'hui)**. Le jour où le matricule
national malien se généralise, il devient la clé inter-écoles — **sans rien casser**.

Comportement de l'identité face aux événements :
- **Redoublement** : identité + matricule inchangés, seule l'inscription annuelle change.
- **Passage de classe** : idem, l'inscription change, l'identité non.
- **Transfert** : nouvelle école = nouveau matricule local + nouveau code de connexion ; l'historique
  reste chez l'école d'origine.

## Point de design à traiter le jour de l'implémentation

**Parent multi-écoles.** Un parent peut avoir des enfants dans deux écoles. Le téléphone est
unique au monde → 1 seul compte parent, lié à plusieurs enfants. Mais aujourd'hui c'est le
directeur de chaque école qui lie parent↔enfant ([guardian_add](../apps/students/views.py)). Il
faut un mécanisme « retrouver le compte parent existant par téléphone et le lier » **sans** que
École B ne voie les enfants de École A. Solvable, mais à concevoir explicitement.

## Sources
- Fiches d'inscription réelles Bamako (École les Lauréats, Bilingual School of Bamako).
- Tendance matricule national Mali (MENA/DESPS, procédures 2024-2026).
- Confrontation Gemini / ChatGPT (juillet 2026).
