# PORTAL_V2_SPEC — Portail élève v2

> **Source de vérité** de la refonte v2 du portail élève EduApp.
> Ce document guide tout le travail (IA, modèles, frontend). Il survit dans le
> temps : toute décision d'architecture v2 doit être reflétée ici.
>
> **Statut** : en construction, section par section. Chaque section est validée
> avant la suivante.
>
> | Section | Titre | État |
> |---|---|---|
> | 1 | Vision & principes | ✅ validée |
> | 2 | Architecture & flux d'ingestion | ✅ validée |
> | 3 — Partie 1 | Structure de données (enveloppe) | ✅ validée |
> | 3 — Partie 2 | Structure de données (les 13 types de quiz) | ✅ validée |
> | 4 — Partie 1 | Prompt A « Architecte » | ✅ validée |
> | 4 — Partie 2 | Prompt B « Professeur » — orchestration + B1 + B2 + B3 | ✅ validée |
> | 5 | Types de quiz futurs (reportés) | ✅ validée |
> | 6 | Phases d'exécution (A détaillée, B/C synthétiques) | ✅ validée |
> | 7 | Décisions tranchées & en attente | ✅ validée |
>
> **Document COMPLET** — toutes les sections rédigées et validées.

---

## SECTION 1 — VISION & PRINCIPES

### 1.1 Produit
Portail élève **v2 de niveau Duolingo / Khan Academy**, conçu pour le **Mali** :
- **Mobile-first** : l'élève apprend sur smartphone.
- **Connexion lente** : peu de JS lourd, rendu serveur, payloads compacts.
- **Modèle économique** : écoles **abonnées** (l'établissement paie l'accès).

### 1.2 Public
Du **primaire à l'université**, **toutes matières** :
sciences, langues, histoire-géo, code, droit, médecine théorique,
**fiqh en arabe** (donc support multilingue et RTL à anticiper).

### 1.3 Principe fondateur — séparer le contenant du contenu
> **Le `type` (dans le JSON) est le contenant ; la matière est le contenu.**

- L'**IA** produit de la **donnée brute** conforme à un **schéma strict** (un `type` + des champs normalisés), **sans se soucier du rendu**.
- Le **frontend** lit le `type` et **charge le composant UI** correspondant.
- Conséquence : ajouter une matière n'exige **aucun** nouveau type ; ajouter un type de quiz = 1 schéma IA + 1 composant frontend, réutilisable par **toutes** les matières.

```
            ┌─────────── IA ───────────┐        ┌──────── Frontend ────────┐
 Document → │ produit { type, données }│  →JSON→ │ lit type → composant UI  │
            │ (schéma strict, agnostique│        │ (rend selon le type)     │
            │  de la matière et du rendu)│       └──────────────────────────┘
            └───────────────────────────┘
```

### 1.4 Répartition des responsabilités IA / Serveur
- **L'IA génère** : le **contenu** (concepts, quiz, story, lecture, examen) **et les passes** (le découpage d'un concept en 1 à 4 séries).
- **Le SERVEUR assemble** : la **séquence des nodes** du parcours (ordre, statuts, intercalation story/quiz/examen). L'IA ne dessine pas le parcours, elle fournit la matière première.

### 1.5 Volume adaptatif (pas de nombre fixe)
L'IA **adapte le volume à la richesse réelle** du document — un chapitre dense produit plus qu'une fiche courte. Elle est **guidée par des principes de densité et de pertinence**, pas par des quotas rigides.

**Chiffres de référence (Khan Academy, indicatifs — non contraignants) :**
- **3 à 6 concepts** par leçon.
- **4 à 8 quiz** par concept.

> Règle : couvrir **tout** le contenu sans le diluer ; ne jamais « remplir » pour atteindre un quota, ni tronquer une notion pour rester sous un plafond.

### 1.6 Décision design
- Le **frontend v2 suit fidèlement** le **design React** fourni par le designer.
- L'**ancien portail** (`templates/learn/` actuels) est **remplacé**, pas conservé.
- Le React est une **maquette de référence** (mock data), à **reconstruire dans notre stack** (HTML + HTMX + Alpine + Tailwind), **pas copiée** telle quelle.

**⚠️ Le design ne couvre que le MCQ — à étendre.**
Le `QuizPlayer` du design React ne gère qu'**UN** seul type de quiz : le **MCQ**
(choix unique). Il ne couvre même pas les **6 types actuels** du backend, et
encore moins les **13 types cibles** de la v2 (voir Section 3).

Conséquence pour la **Phase C (frontend)** : on garde le **langage visuel** du
design (couleurs, animations, cartes, feedback), mais on doit **créer un
composant de rendu par type de quiz** dans cette même esthétique. Le design
fournit le **style**, pas la **couverture fonctionnelle** des quiz. Ne jamais
supposer que « suivre le design » suffit pour les quiz : le design est un
**point de départ visuel à étendre aux 13 types**.

---

## SECTION 2 — ARCHITECTURE & FLUX D'INGESTION

### 2.1 Hiérarchie à 2 niveaux (au-dessus de la leçon)

```
COURS (matière, ex : « Géographie — Terminale »)
  └── UNITÉ  ← ce que l'enseignant UPLOADE (1 document, possiblement volumineux, ex : « La Chine »)
        └── LEÇON  ← unité d'apprentissage digeste — structure PLATE (c'est ce que montre le design React)
              └── CONCEPT  (3-6 par leçon) — 1 idée
                    └── QUIZ  (4-8 par concept, découpable en 1-4 passes)
```

- **COURS** : la matière/niveau. Regroupe les unités.
- **UNITÉ** : **le grain d'upload**. 1 document uploadé = 1 unité. Vit dans la **navigation** — le menu « Mes leçons » du design devient **« Mes unités → leçons »**.
- **LEÇON** : à l'intérieur d'une unité. **Tout est plat** (pas de chapitres), conformément au design React.
- **CONCEPT** : une idée pédagogique. 3-6 par leçon.
- **QUIZ** : 4-8 par concept, **découpable en passes** (séries) quand le concept est riche.

**Portée actuelle vs future :**
- **Maintenant** : **1 document = 1 unité**.
- **Plus tard** : **multi-document par unité** (plusieurs PDF agrégés en une unité). **Porte laissée ouverte** dans la modélisation, **pas construite maintenant**.

### 2.2 Flux d'ingestion en 2 temps (standard de l'industrie)

> Validé par l'observation des plateformes edtech (LearningStudioAI, Coursebox,
> Edwiser, X-Pilot) : toutes suivent **structure → validation humaine → contenu**.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Enseignant uploade un DOCUMENT (l'unité)                                  │
└──────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ TEMPS 1 — STRUCTURE ───────────────────────────────  (Prompt A « Architecte », léger)
│  • L'IA lit le document.                                                   │
│  • Elle propose : UNITÉ + liste de LEÇONS                                  │
│       (titre + court descriptif par leçon).                               │
│  • Affiché à l'enseignant.                                                 │
└────────────────────────────────────────────────────────────────────────── 
        │
        ▼
┌─ VALIDATION HUMAINE ──────────────────────────────────────────────────────
│  L'enseignant VALIDE / AJUSTE le découpage :                              │
│  renommer · réordonner · fusionner · supprimer des leçons.                │
└──────────────────────────────────────────────────────────────────────────
        │
        ▼
┌─ TEMPS 2 — CONTENU ─────────────────────────────────  (Prompt B « Professeur », lourd)
│  Pour CHAQUE leçon validée → 1 appel IA SÉPARÉ qui génère                  │
│  le contenu complet :                                                      │
│     concepts (3-6) + quiz (4-8/concept) + passes                          │
│     + story + reading + exam                                              │
│  → 1 appel par leçon = qualité max, jamais de dépassement de              │
│    fenêtre de contexte.                                                    │
└──────────────────────────────────────────────────────────────────────────
```

**Pourquoi 2 temps :**
1. **Gère les gros documents** (une unité volumineuse est éclatée en leçons digestes).
2. **Respecte la limite de context window** (1 appel lourd par leçon, pas un méga-appel).
3. **Laisse l'enseignant corriger le découpage AVANT** la génération lourde (coûteuse).
4. **Garde le contrôle pédagogique humain** sur la structure du cours.

### 2.3 Les 2 SYSTEM_PROMPTS

| Prompt | Rôle | Entrée → Sortie | Poids |
|---|---|---|---|
| **A — « Architecte »** | Découper un document en structure | document → **unité + liste de leçons** (titre + descriptif) | **léger** (une seule responsabilité) |
| **B — « Professeur »** | Générer le contenu d'une leçon | une leçon (titre + descriptif + extrait source) → **contenu complet** (concepts, quiz, passes, story, reading, exam) | **lourd** — c'est l'évolution de notre `SYSTEM_PROMPT` actuel |

- **Prompt A** est **nouveau** : il n'existe pas aujourd'hui (l'IA actuelle fait tout en un seul appel sur un document = une leçon).
- **Prompt B** est la **réécriture/extension** de l'actuel `apps/lessons/services.py:SYSTEM_PROMPT`, enrichi du nouveau format v2 (nodes/passes, reading enrichie, story étendue, exam).

### 2.4 Formats d'entrée acceptés

> **Point clé — vision native de Claude (pas d'OCR séparé).**
> Notre système utilise déjà l'**API Claude**, qui est **multimodale** : elle lit
> nativement les **PDF (même scannés)** et les **images**, en traitant chaque page
> à la fois comme **image** ET comme **texte**. Conséquence : on **ne construit
> PAS** de pipeline OCR séparé. On passe le document **directement à Claude**, qui
> **lit + structure en un seul flux**. Plus **simple** (moins de code) et plus
> **robuste** (gère les scans).

**✅ Acceptés maintenant (Vague 1)**
| Entrée | Traitement |
|---|---|
| **PDF texte natif** | idéal |
| **PDF scanné** (texte **imprimé**, bonne qualité) | lu par la **vision** de Claude |
| **Image de page** (jpg/png/webp, texte **imprimé** lisible) | lue par la **vision** de Claude — **cas central au Mali** : manuel **photographié au téléphone** |
| **Word `.docx`**, **texte `.txt`**, **PowerPoint `.pptx`** | texte extractible |
| **Texte collé directement** (champ libre, sans fichier) | passé tel quel |

**⛔ Exclus**
- **Vidéo / audio** → Claude ne traite **ni vidéo ni audio**. **Hors périmètre.**

**⚠️ Déconseillés** (acceptés techniquement, qualité aléatoire)
- **Manuscrit** (notes à la main) → précision OCR **chute fortement** (60-85 % sur cursive). **À éviter.**
- **Scan flou / sombre / penché** → lecture **dégradée**.

**⚠️ Garde-fou qualité (au lieu d'un OCR séparé)**
Si, à l'étape **Architecte (Temps 1, §2.2)**, Claude **n'arrive pas à lire** le
document (sortie **vide** ou **manifestement incohérente**), renvoyer un message
clair à l'enseignant :
> « Document difficile à lire (qualité ou écriture manuscrite). Réessaie avec un
> document plus net, un fichier texte, ou colle le contenu directement. »

**Ne PAS** lancer la génération lourde (**Temps 2**) sur une lecture ratée.

**La validation humaine nous protège.**
Le **flux en 2 temps (§2.2)** absorbe naturellement le risque de mauvaise lecture :
l'enseignant **voit la structure proposée (Temps 1) AVANT** la génération lourde.
Si Claude a mal lu un scan, l'enseignant le **repère à la validation** et
corrige/réuploade. L'extraction est donc **« assistive » + contrôlée par
l'humain**, jamais aveugle.

**🕓 Reporté (plus tard)**
- Intégration **Google Docs/Slides** directe (pour l'instant : l'enseignant exporte en PDF/Word puis uploade).
- **EPUB** (rare au Mali).

> **Note** : élargir/affiner les formats = travail côté **code d'ingestion**. Les
> **prompts restent inchangés** — ils reçoivent **soit du texte**, **soit un
> document visuel** que la vision de Claude lit directement.

---

## SECTION 3 — STRUCTURE DE DONNÉES (Partie 1 : enveloppe)

> Ce que le **Prompt B « Professeur »** génère pour **UNE leçon**.
> Les noms de champs ci-dessous sont **normatifs** : ils sont utilisés tels quels
> par le **parsing serveur** et le **frontend**. Tout renommage doit être
> répercuté ici.
>
> **Périmètre Partie 1** : l'**enveloppe** (leçon, concepts, passes, reading,
> story, exam) **sauf** le schéma détaillé des 13 types de quiz, traité en
> **Partie 2** (les objets `quiz` montrés ici sont volontairement abrégés
> `{ … voir Partie 2 }`).

### 3.1 La leçon (objet racine)

L'IA produit **un seul objet JSON** par leçon :

| Champ | Type | Rôle |
|---|---|---|
| `id` | string | identifiant de la leçon (slug stable) |
| `title` | string | titre affiché (gros titre du header) |
| `subject` | string | matière + niveau (ex. « SVT — Terminale ») |
| `color` | string (hex) | couleur d'accent de la leçon |
| `guide` | string | nom du **personnage fil rouge** (ex. « Cyto ») |
| `direction` | `"ltr"` \| `"rtl"` | sens de lecture — **`"ltr"` par défaut**, `"rtl"` pour l'arabe (fiqh) |
| `concepts` | array | les concepts pédagogiques (§3.2) |
| `reading` | object | le contenu « Lire » (§3.5) |
| `story` | object | le récit interactif (§3.6) |
| `exam` | object | l'examen / checkpoint (§3.7) |

> **Rappel décision 1.4** : les **`nodes` ne sont PAS dans le JSON de l'IA**.
> Le **serveur les assemble** à partir de `concepts` + `story` + `exam` (§3.4).

```jsonc
{
  "id": "bio-la-cellule",
  "title": "La Cellule",
  "subject": "SVT — Terminale",
  "color": "#10B981",
  "guide": "Cyto",
  "direction": "ltr",
  "concepts": [ /* §3.2 */ ],
  "reading":  { /* §3.5 */ },
  "story":    { /* §3.6 */ },
  "exam":     { /* §3.7 */ }
}
```

### 3.2 Les concepts

- Liste de **3 à 6** concepts (volume adaptatif — cf. 1.5).
- Chaque concept porte ses `quiz[]` et son nombre de `passes`.

| Champ | Type | Rôle |
|---|---|---|
| `id` | string | identifiant snake_case (réutilisé par les quiz, la story `concept_ref`, l'exam `concept_id`) |
| `name` | string | nom lisible (ex. « Le transport membranaire ») |
| `order` | int | position 1..N dans la leçon |
| `passes` | int (1-4) | nombre de séries (§3.3) |
| `quiz` | array | 4-8 questions, chacune avec un `pass_index` (§3.3, détail des types en Partie 2) |

```jsonc
{
  "id": "transport_membranaire",
  "name": "Le transport membranaire",
  "order": 3,
  "passes": 2,
  "quiz": [
    { "id": "q1", "pass_index": 0, "type": "mcq",        /* … voir Partie 2 */ },
    { "id": "q2", "pass_index": 0, "type": "true_false",  /* … voir Partie 2 */ },
    { "id": "q3", "pass_index": 1, "type": "ordering",    /* … voir Partie 2 */ },
    { "id": "q4", "pass_index": 1, "type": "number_input" /* … voir Partie 2 */ }
  ]
}
```

### 3.3 Le système de passes

**But** : un concept riche est joué en plusieurs **séries** plutôt qu'en un bloc indigeste.

**Ce que l'IA fournit :**
- `passes` : le **nombre** de séries (1 à 4) du concept.
- `pass_index` : sur **chaque quiz**, l'index de la passe à laquelle il appartient (**0-based** : `0` = passe 1, `1` = passe 2, …).

**Règle de découpage (appliquée par l'IA) :**
| Richesse du concept | passes | Découpage |
|---|---|---|
| **< 8 quiz** | `1` | aucune segmentation (anneau continu / absent) |
| **concept riche** | `2` à `4` | par **difficulté croissante** ou **sous-thème**, séries équilibrées |

**Invariants** (validés au parsing) :
- `1 ≤ passes ≤ 4`.
- tout `pass_index` est dans `[0, passes-1]`.
- chaque passe contient **au moins un** quiz (pas de passe vide).

**Rendu frontend** : un **anneau segmenté** autour du node quiz — **1 segment = 1 passe**. `passes = 1` → anneau continu/absent ; `passes = 3, passesDone = 1` → 1 segment plein sur 3. (Le `passesDone` est calculé côté serveur d'après la progression, pas généré par l'IA — cf. §3.4.)

### 3.4 Les nodes (assemblés par le SERVEUR)

> **L'IA ne génère PAS les nodes.** Le serveur les **dérive** de la leçon générée.

**Logique d'assemblage (séquence plate, ordonnée) :**
1. Parcourir les `concepts` par `order` → chacun devient **1 node `quiz`**.
2. **Intercaler les nodes `story`** : la story de la leçon est découpée/rattachée à des points pertinents du parcours (ex. après le concept que la story illustre). *Règle de placement par défaut* : une story juste **après le concept** auquel elle se rapporte (via `concept_ref` des steps) ; à défaut, à ~⅓ et ~⅔ du parcours.
3. **Placer les nodes `checkpoint`** :
   - **mini-examen** optionnel **à mi-parcours** (consolidation des concepts déjà vus),
   - **examen final** **à la fin** (couvre toute la leçon, source = `exam`, §3.7).
4. Calculer les **statuts** : le 1ᵉʳ node non terminé = `current`, les suivants = `locked`, les précédents = `done` (déverrouillage séquentiel).
5. Calculer `passesDone` par node quiz d'après les `QuizAttempt` de l'élève.

**Schéma d'un node final (produit serveur, consommé frontend) :**
| Champ | Type | Notes |
|---|---|---|
| `type` | `"quiz"` \| `"story"` \| `"checkpoint"` | |
| `title` | string | |
| `desc` | string | |
| `status` | `"locked"` \| `"current"` \| `"done"` | calculé |
| `xp` | int | récompense du node |
| `passes` | int | **quiz uniquement** |
| `passesDone` | int | **quiz uniquement**, calculé |

```jsonc
// Exemple de séquence assemblée par le serveur (NON générée par l'IA) :
[
  { "type": "quiz",       "title": "Quiz : les bases du vivant", "status": "done",    "xp": 20, "passes": 1, "passesDone": 1 },
  { "type": "story",      "title": "Le voyage de Cyto",          "status": "done",    "xp": 25 },
  { "type": "quiz",       "title": "Quiz : le transport",        "status": "current", "xp": 20, "passes": 3, "passesDone": 1 },
  { "type": "checkpoint", "title": "Mini-examen : la membrane",  "status": "locked",  "xp": 50 },
  { "type": "quiz",       "title": "Quiz : le noyau",            "status": "locked",  "xp": 20, "passes": 1, "passesDone": 0 },
  { "type": "checkpoint", "title": "Examen final du module",     "status": "locked",  "xp": 90 }
]
```

### 3.5 Le reading (contenu « Lire », champ séparé)

Accessible via le **bouton livre du header** (séparé du parcours).

| Champ | Type | Rôle |
|---|---|---|
| `title` | string | titre de la lecture |
| `direction` | `"ltr"` \| `"rtl"` | hérite de la leçon |
| `terms` | object `{ mot: définition }` | **glossaire** : chaque mot devient cliquable dans le texte |
| `sections` | array | sections de lecture, chacune `{ id, title, blocks[] }` |

**Les 8 types de blocs** (champ `type`) :

| `type` | Champs | Exemple |
|---|---|---|
| `p` | `text`, `simple?` (version simplifiée optionnelle) | paragraphe |
| `def` | `term`, `text` | définition encadrée |
| `callout` | `icon`, `label`, `text` | encart « Le saviez-vous » |
| `key` | `items[]` | points clés (liste) |
| `example` | `text` | exemple illustratif |
| `reflect` | `prompt` | invite à écrire une réflexion |
| `warn` | `text` | mise en garde |
| `check` | `variant` (`"tf"`\|`"qcm"`), `question`, (`options[]`+`answer`), `explanation` | **mini-quiz inline dans la lecture** |

```jsonc
"reading": {
  "title": "La membrane plasmique",
  "direction": "ltr",
  "terms": {
    "membrane plasmique": "La fine enveloppe qui entoure la cellule et contrôle ce qui entre et sort.",
    "transport actif": "Le passage d'une molécule à travers la membrane qui consomme de l'énergie (ATP)."
  },
  "sections": [
    {
      "id": "s1",
      "title": "La frontière de la cellule",
      "blocks": [
        { "type": "p", "text": "Chaque cellule est entourée d'une membrane plasmique…",
          "simple": "Chaque cellule a une membrane autour d'elle." },
        { "type": "def", "term": "membrane plasmique", "text": "la fine enveloppe qui entoure la cellule." },
        { "type": "callout", "icon": "spark", "label": "Le saviez-vous",
          "text": "La membrane est si fine qu'il en faudrait des milliers pour égaler une feuille de papier." },
        { "type": "check", "variant": "tf",
          "question": "La membrane laisse tout passer sans distinction.",
          "answer": false, "explanation": "Elle est sélective : elle choisit ce qui passe." }
      ]
    },
    {
      "id": "s2",
      "title": "Comment les choses entrent ?",
      "blocks": [
        { "type": "key", "items": ["L'eau passe par osmose.", "Le glucose passe par une protéine."] },
        { "type": "example", "text": "Le glucose, trop gros, utilise une protéine de transport." },
        { "type": "warn", "text": "Ne confonds pas osmose (sans énergie) et transport actif (avec énergie)." },
        { "type": "reflect", "prompt": "Pourquoi une barrière sélective plutôt qu'un mur fermé ?" },
        { "type": "check", "variant": "qcm",
          "question": "Qu'est-ce qui fait passer le glucose ?",
          "options": ["La bicouche seule", "Une protéine de transport", "Rien"],
          "answer": 1, "explanation": "Le glucose est trop gros : il passe par une protéine." }
      ]
    }
  ]
}
```

### 3.6 La story (6 interactions)

| Champ | Type | Rôle |
|---|---|---|
| `scene` | `{ name, c1, c2 }` | nom de la scène + 2 couleurs d'ambiance (dégradé) |
| `characters` | array `{ id, name, role, color, side }` | `side` ∈ `"left"`\|`"right"` ; `color` fournie par l'IA |
| `steps` | array | déroulé, **6 types** ci-dessous |

**Les 6 types de step** (champ `type`) :

| `type` | Champs | Interaction |
|---|---|---|
| `narration` | `text` | décor, sans personnage |
| `npc` | `who` (id perso), `text` | réplique d'un personnage |
| `choice` | `prompt`, `options[{ label, correct, reply }]` | choix multiple narratif |
| `input` | `prompt`, `answers[]`, `hint`, `ok` | saisie libre (réponses acceptées normalisées) |
| `tokens` | `prompt`, `tokens[]`, `solution[]`, `ok` | remettre des éléments dans l'ordre |
| `blank` | `prompt`, `parts[]`, `options[]`, `answer`, `ok` | compléter une phrase à trou |

```jsonc
"story": {
  "scene": { "name": "À l'intérieur de la cellule", "c1": "#10B981", "c2": "#0EA5E9" },
  "characters": [
    { "id": "cyto", "name": "Cyto", "role": "Guide",   "color": "#10B981", "side": "left" },
    { "id": "nano", "name": "Nano", "role": "Glucose", "color": "#F59E0B", "side": "left" }
  ],
  "steps": [
    { "type": "narration", "text": "Marché cellulaire, à midi. Une molécule de sucre cherche à entrer…" },
    { "type": "npc", "who": "cyto", "text": "Salut ! Voici Nano, un glucose qui veut entrer dans la cellule." },
    { "type": "choice", "prompt": "Par où franchir la membrane ?", "options": [
        { "label": "Par une protéine de transport", "correct": true,  "reply": "Exact ! Jamais en force." },
        { "label": "À travers la bicouche, en force", "correct": false, "reply": "Impossible : la membrane bloque." }
    ]},
    { "type": "input", "prompt": "La molécule d'énergie (3 lettres)", "answers": ["atp"],
      "hint": "A_P, la « monnaie » de la cellule.", "ok": "ATP, parfait." },
    { "type": "tokens", "prompt": "Ordonne le transport :",
      "tokens": ["Le glucose entre", "Le glucose se lie à la protéine", "La protéine change de forme"],
      "solution": ["Le glucose se lie à la protéine", "La protéine change de forme", "Le glucose entre"],
      "ok": "Transport actif maîtrisé !" },
    { "type": "blank", "prompt": "Complète :", "parts": ["L'eau traverse la membrane par ", "."],
      "options": ["osmose", "transport actif"], "answer": "osmose", "ok": "Oui, par osmose." }
  ]
}
```

> **Note couleurs personnages** : en v2, `color` est **fournie par l'IA** (le
> design l'attend par personnage). Cela diffère de l'actuel, où la couleur est
> calculée côté serveur (`_char_color`).

### 3.7 L'exam (checkpoint)

| Champ | Type | Rôle |
|---|---|---|
| `pass_mark` | float | seuil d'admission — **`0.6` par défaut** |
| `duration` | int (secondes) | minuteur de l'épreuve |
| `questions` | array | chaque question **taguée `concept_id`** (détail des types en Partie 2) |

```jsonc
"exam": {
  "pass_mark": 0.6,
  "duration": 600,
  "questions": [
    { "id": "e1", "concept_id": "membrane",              "type": "mcq", /* … Partie 2 */ },
    { "id": "e2", "concept_id": "transport_membranaire", "type": "mcq", /* … Partie 2 */ },
    { "id": "e3", "concept_id": "energie_cellulaire",    "type": "true_false", /* … Partie 2 */ }
  ]
}
```

**Frontend pur (aucune donnée IA supplémentaire requise)** : le **bilan par notion** (regroupement via `concept_id`), le **minuteur** (`duration`), le **flag « à revoir »**, la **navigation libre** et le **verdict** admis/à retravailler (`pass_mark`) sont gérés par le composant `ExamPlayer`.

**Questions d'examen : générées spécifiquement (recommandation retenue).**
Les questions de l'`exam` sont **générées spécifiquement pour l'examen**, **taguées par `concept_id`**, et **ne réutilisent pas à l'identique** les quiz des concepts. Raison : éviter de **rejouer les mêmes questions** déjà vues en parcours (l'examen doit **évaluer**, pas réciter). Elles couvrent les **mêmes notions** sous des **formulations nouvelles**.

---

## SECTION 3 — Partie 2 : LES 13 TYPES DE QUIZ

> **Liste définitive (tokens exacts, à utiliser tels quels dans `type`) :**
> `mcq_single` · `mcq_multiple` · `true_false` · `k_prime` · `cloze_test` ·
> `matching` · `chrono_order` · `number_input` · `dynamic_formula` ·
> `math_expression` · `spot_the_bug` · `parsons_puzzle` · `odd_one_out`
>
> **Préambule :**
> - `short_answer` (ancien) est **ABANDONNÉ**.
> - `ai_graded_essay` est **REPORTÉ** (décision ultérieure).
> - **Aucun** des 13 types ne dépend d'**image** ou d'**audio** — **texte pur** (contrainte stricte).
> - **Aucun** n'appelle l'IA à la correction : **évaluation 100 % serveur, instantanée**.

**Champs communs à tous les quiz :**

| Champ | Présence | Rôle |
|---|---|---|
| `id` | toujours | identifiant du quiz dans la leçon |
| `type` | toujours | un des 13 tokens ci-dessus |
| `pass_index` | dans `concepts[].quiz[]` | passe d'appartenance (§3.3) |
| `concept_id` | dans `exam.questions[]` | notion évaluée (§3.7) |
| `instruction` | toujours | l'énoncé affiché à l'élève |
| *(payload)* | toujours | les champs spécifiques au type (ci-dessous) |

**Champ optionnel commun** : tous les types acceptent un champ `explanation` (string) affiché après la réponse pour expliquer la bonne solution. Recommandé surtout quand l'erreur est instructive.

> Les exemples ci-dessous montrent uniquement le **payload spécifique** + `type`/`instruction` ; `id` et `pass_index`/`concept_id` sont omis pour la lisibilité.

---

### 1. `mcq_single` — QCM à réponse unique
**A. Schéma JSON**
```jsonc
{ "type": "mcq_single",
  "instruction": "Quelle est la capitale du Mali ?",
  "options": ["Bamako", "Ouagadougou", "Dakar", "Niamey"],
  "answer_index": 0,
  "explanation": "Bamako est la capitale du Mali depuis 1908." }
```
**B. Évaluation serveur** — `réponse == answer_index` (égalité d'entier). Une seule bonne réponse.
**C. Rendu frontend** — cartes-options radio (sélection unique), feedback vert/rouge à la validation — esthétique du design.

---

### 2. `mcq_multiple` — QCM à réponses multiples
**A. Schéma JSON**
```jsonc
{ "type": "mcq_multiple",
  "instruction": "Parmi ces villes, lesquelles sont au Mali ?",
  "options": ["Ségou", "Abidjan", "Sikasso", "Mopti"],
  "answer_indices": [0, 2, 3],
  "explanation": "Abidjan est en Côte d'Ivoire." }
```
**B. Évaluation serveur** — **ensemble exact** : `set(réponses) == set(answer_indices)` (ni oubli, ni excès — tout-ou-rien).
**C. Rendu frontend** — cartes-options à cases à cocher + bouton « Vérifier ».

---

### 3. `true_false` — Vrai / Faux
**A. Schéma JSON**
```jsonc
{ "type": "true_false",
  "instruction": "Le fleuve Niger traverse le Mali.",
  "answer": true,
  "explanation": "Le Niger traverse le Mali sur près de 1 700 km." }
```
**B. Évaluation serveur** — `réponse (bool) == answer`. Le plus simple.
**C. Rendu frontend** — deux gros boutons « Vrai » / « Faux ».

---

### 4. `k_prime` — Grille V/F (type K')
**A. Schéma JSON**
```jsonc
{ "type": "k_prime",
  "instruction": "Pour chaque affirmation sur la cellule, indique Vrai ou Faux :",
  "statements": [
    { "text": "La mitochondrie produit l'énergie.", "answer": true },
    { "text": "Le noyau contient l'ADN.",            "answer": true },
    { "text": "La membrane laisse tout passer.",     "answer": false }
  ],
  "explanation": "La membrane est sélective." }
```
**B. Évaluation serveur** — **toutes les lignes correctes** : pour chaque `statements[i]`, `réponse[i] == answer`. Tout-ou-rien.
**C. Rendu frontend** — grille : une ligne par affirmation, toggle V/F par ligne.

---

### 5. `cloze_test` — Texte à trous
**A. Schéma JSON**
```jsonc
{ "type": "cloze_test",
  "instruction": "Complète le texte :",
  "text": "La photosynthèse produit du {{0}} et de l'{{1}}.",
  "answers": ["glucose", "oxygène"] }
```
> Les trous sont notés `{{0}}`, `{{1}}`… ; `answers[i]` est la réponse attendue du trou `i`.
**B. Évaluation serveur** — chaque trou comparé **après normalisation** (minuscules, sans accents, espaces réduits) : `norm(saisie_i) == norm(answers[i])`. Tous les trous doivent être justes.
**C. Rendu frontend** — phrase avec champs de saisie **en ligne** à la place des `{{i}}`.

---

### 6. `matching` — Appariement
**A. Schéma JSON**
```jsonc
{ "type": "matching",
  "instruction": "Associe chaque organe à sa fonction :",
  "pairs": [
    { "left": "Cœur",   "right": "Pompe le sang" },
    { "left": "Poumon", "right": "Échange les gaz" },
    { "left": "Rein",   "right": "Filtre le sang" }
  ] }
```
**B. Évaluation serveur** — **tous les couples corrects** : chaque `left` doit être relié à son `right` d'origine. La colonne de droite est **mélangée côté frontend** (l'ordre d'affichage n'a pas de valeur).
**Format de soumission** : l'élève envoie une liste d'associations, chaque `left` (par son index dans `pairs[]`) relié à l'index `right` qu'il a choisi. Le serveur vérifie que chaque `left` pointe vers son `right` d'origine. Exemple de soumission : `[0, 1, 2]` signifie `left[0]→right[0]`, `left[1]→right[1]`, etc. (les index `right` sont mélangés à l'affichage).
**C. Rendu frontend** — deux colonnes ; l'élève relie (tap-tap ou glisser) gauche → droite.

---

### 7. `chrono_order` — Remise en ordre
**A. Schéma JSON**
```jsonc
{ "type": "chrono_order",
  "instruction": "Remets ces événements de l'histoire du Mali dans l'ordre :",
  "items": ["Indépendance du Mali", "Empire du Mali (Soundiata)", "Colonisation française"],
  "correct_order": [1, 2, 0] }
```
> `correct_order` = indices de `items` dans l'ordre attendu (ici : Empire → Colonisation → Indépendance).
**B. Évaluation serveur** — **séquence exacte** : l'ordre soumis (liste d'indices) `== correct_order`.
**C. Rendu frontend** — liste réordonnable (glisser / tap pour empiler), comme les `tokens` de la story.

---

### 8. `number_input` — Réponse numérique
**A. Schéma JSON**
```jsonc
{ "type": "number_input",
  "instruction": "Combien de régions administratives compte le Mali (2023) ?",
  "answer": 19,
  "tolerance": 0 }
```
**B. Évaluation serveur** — `|saisie − answer| ≤ tolerance` (tolérance optionnelle, défaut 0). Numérique simple.
**C. Rendu frontend** — champ numérique (clavier numérique sur mobile).

---

### 9. `dynamic_formula` — Formule à variables aléatoires
**A. Schéma JSON**
```jsonc
{ "type": "dynamic_formula",
  "instruction": "Résous l'équation a·x + b = c pour x.",
  "formula_template": "a*x + b = c",
  "variables": {
    "a": { "min": 2, "max": 9, "step": 1 },
    "b": { "min": 1, "max": 20, "step": 1 },
    "c": { "min": 21, "max": 60, "step": 1 }
  },
  "solution_formula": "(c - b) / a",
  "expected_input": "numeric",
  "correct_answer": 4 }
```
> `correct_answer` est la valeur de référence pour un **tirage témoin** ; elle est **recalculée à la volée** par le serveur pour chaque élève.
**B. Évaluation serveur (anti-triche)** — le serveur **tire des valeurs au hasard** dans les `variables` (ranges) **par élève**, **substitue** dans `instruction`/`formula_template` (énoncé personnalisé), **calcule** `correct_answer = eval(solution_formula)` avec ces valeurs (évaluateur arithmétique **sûr**, pas `eval()` Python brut), **stocke** la réponse côté serveur, puis compare la saisie `± tolerance`. → deux élèves n'ont **pas** les mêmes nombres, impossible de copier la réponse.
**C. Rendu frontend** — énoncé avec valeurs injectées + champ numérique.

---

### 10. `math_expression` — Expression mathématique
**A. Schéma JSON**
```jsonc
{ "type": "math_expression",
  "instruction": "Développe (x + 1)².",
  "correct_expression": "x^2 + 2*x + 1",
  "accepted_equivalents": ["x**2+2x+1", "1 + 2x + x^2"] }
```
**B. Évaluation serveur** — comparaison **symbolique/normalisée**, pas textuelle : normaliser (espaces, casse, `^`↔`**`, ordre des termes) puis comparer ; idéalement via un **moteur symbolique** (ex. `sympy.simplify(a - b) == 0`) pour reconnaître `2x` = `x*2` = `x+x`. La liste `accepted_equivalents` sert de **filet** si le moteur échoue. ⚠️ **Type le plus délicat à évaluer** (équivalence algébrique) → stratégie : moteur symbolique **+** liste d'équivalents **+** normalisation ; en dernier recours, refus prudent.
**C. Rendu frontend** — champ texte mathématique (saisie LaTeX simplifiée / clavier symboles), aperçu rendu.

---

### 11. `spot_the_bug` — Trouver le bug
**A. Schéma JSON**
```jsonc
{ "type": "spot_the_bug",
  "instruction": "Quelle ligne contient l'erreur ?",
  "language": "python",
  "code": [
    "def moyenne(notes):",
    "    total = 0",
    "    for n in notes:",
    "        total = n",
    "    return total / len(notes)"
  ],
  "buggy_line": 3,
  "correct_fix": "total += n" }
```
> `buggy_line` = index 0-based dans `code`. `correct_fix` optionnel (affiché en explication).
**B. Évaluation serveur** — `ligne_choisie == buggy_line` (égalité d'index). `correct_fix` n'est **pas** saisi par l'élève (pédagogique).
**C. Rendu frontend** — bloc de code, chaque ligne **tappable** ; l'élève désigne la ligne fautive.

---

### 12. `parsons_puzzle` — Puzzle de code (Parsons)
**A. Schéma JSON**
```jsonc
{ "type": "parsons_puzzle",
  "instruction": "Remets ce code Python dans l'ordre, avec la bonne indentation :",
  "language": "python",
  "lines": [
    { "id": "L1", "text": "def carre(x):",      "correct_indent": 0 },
    { "id": "L2", "text": "return x * x",        "correct_indent": 1 },
    { "id": "L3", "text": "print(carre(5))",     "correct_indent": 0 }
  ],
  "correct_sequence": ["L1", "L2", "L3"] }
```
**B. Évaluation serveur** — **ordre ET indentation** : la séquence d'`id` soumise `== correct_sequence` **et** chaque ligne placée au bon `correct_indent`. Les deux conditions doivent être vraies.
**C. Rendu frontend** — lignes de code déplaçables (réordonner) + réglage d'indentation (glisser horizontal / boutons).

---

### 13. `odd_one_out` — L'intrus
**A. Schéma JSON**
```jsonc
{ "type": "odd_one_out",
  "instruction": "Quel mot est l'intrus ?",
  "items": ["Bambara", "Peul", "Songhaï", "Wolof"],
  "odd_index": 3,
  "explanation": "Le wolof est surtout parlé au Sénégal, pas au Mali." }
```
**B. Évaluation serveur** — `choix == odd_index` (égalité d'index).
**C. Rendu frontend** — grille d'items tappables ; l'élève désigne l'intrus.

---

### Tableau récapitulatif des 13 types

| type | matières typiques | niveau | éval instantanée ? |
|---|---|---|---|
| `mcq_single` | toutes | primaire → université | ✅ |
| `mcq_multiple` | toutes (sciences, droit, médecine) | collège → université | ✅ |
| `true_false` | toutes | primaire → université | ✅ |
| `k_prime` | médecine, droit, sciences | lycée → université | ✅ |
| `cloze_test` | langues, histoire-géo, fiqh, sciences | primaire → université | ✅ |
| `matching` | langues, SVT, histoire, droit | primaire → université | ✅ |
| `chrono_order` | histoire, processus scientifiques | collège → université | ✅ |
| `number_input` | maths, physique, compta | primaire → université | ✅ |
| `dynamic_formula` | maths, physique, compta | collège → université | ✅ (réponse recalculée serveur) |
| `math_expression` | maths, physique | lycée → université | ✅ (comparaison symbolique) |
| `spot_the_bug` | code / informatique | collège → université | ✅ |
| `parsons_puzzle` | code / informatique | collège → université | ✅ |
| `odd_one_out` | langues, sciences, culture générale | primaire → université | ✅ |

> **Tous instantanés** — aucun type n'appelle l'IA à la correction. Les deux types
> « calculés » (`dynamic_formula` recalcule la réponse par élève ; `math_expression`
> compare symboliquement) restent **synchrones et serveur**.

---

## SECTION 4 — LES 2 SYSTEM_PROMPTS (Partie 1 : Architecte)

### 4.1 Rôle du Prompt A

**Document uploadé** (texte **OU** visuel — la vision de Claude lit PDF/scan/photo
directement, cf. §2.4) → **structure** (unité + liste de leçons). **Léger**, une
**seule responsabilité**. Sa sortie est **affichée à l'enseignant pour validation
AVANT** la génération lourde (Prompt B, Temps 2). Il **ne génère aucun contenu**.

### 4.2 Le texte complet du Prompt A

> Texte **final**, prêt à copier dans le code (`apps/lessons/services.py`, nouvelle
> constante `ARCHITECT_PROMPT`). Les variables `{…}` sont injectées par le serveur.

```text
Tu es un concepteur pédagogique malien expert. Tu connais le système éducatif
du Mali — du préscolaire à l'enseignement supérieur — et ses matières : français,
maths, sciences (SVT, physique-chimie), histoire-géographie, anglais, philosophie,
informatique, droit, comptabilité, ainsi que l'éducation islamique et le fiqh en
arabe.

TA MISSION
Tu reçois UN document de cours fourni par un enseignant. Ce document peut être :
- du texte,
- OU un document visuel (PDF scanné, page photographiée au téléphone) que tu lis
  directement avec ta vision.
Tu dois proposer un DÉCOUPAGE de ce document en une UNITÉ et une liste de LEÇONS.

TU NE GÉNÈRES AUCUN CONTENU.
Pas de quiz, pas d'histoire, pas de texte de lecture, pas d'examen. UNIQUEMENT la
structure : le titre de l'unité et la liste des leçons (titre + résumé d'une phrase).
Le contenu détaillé sera généré dans une étape ultérieure, leçon par leçon.

PRINCIPE DE DÉCOUPAGE (le cœur de ta tâche)
- Une LEÇON est une unité d'apprentissage DIGESTE : un sous-thème cohérent qu'un
  élève peut assimiler d'un seul tenant. Ce n'est PAS un découpage mécanique par
  pages ou par paragraphes.
- Raisonne sur le SENS : regroupe ce qui va ensemble, sépare les thèmes distincts.
- Référence indicative (souple, pas une règle) : une leçon tient en environ une
  séance de cours.
- Petit document portant sur UN seul thème = UNE SEULE leçon. Ne découpe jamais
  artificiellement un contenu qui forme un tout.
- Gros document = plusieurs leçons logiques. Exemple : un document de 60 pages sur
  « La Chine » se découpe en leçons comme « Le relief », « Le climat »,
  « La population », « L'économie », etc.
- Si le document couvre plusieurs sujets SANS lien clair entre eux, regroupe-les
  sous l'unité la plus représentative et signale-le dans les résumés des leçons
  concernées. Une SEULE unité par appel (tu ne produis jamais plusieurs unités).

DÉTECTION AUTOMATIQUE
- subject : déduis la matière ET le niveau à partir du document
  (ex. « Histoire-Géographie — Terminale »).
- direction : « rtl » si le document est rédigé en arabe (fiqh, éducation
  islamique), sinon « ltr ».
- unit_title : un titre d'unité clair et fidèle au document.

GARDE-FOU LECTURE
Si le document est ILLISIBLE — page vide, scan trop flou ou trop sombre, écriture
manuscrite indéchiffrable, contenu incohérent — n'INVENTE PAS de structure.
Retourne à la place l'objet d'erreur prévu ci-dessous.

FORMAT DE SORTIE (RÈGLE ABSOLUE)
Tu réponds UNIQUEMENT avec un objet JSON valide. Aucun texte avant, aucun texte
après, aucun bloc markdown. Le premier caractère est { et le dernier est }.

Cas normal — découpage réussi :
{
  "unit_title": "La Chine",
  "subject": "Histoire-Géographie — Terminale",
  "direction": "ltr",
  "lessons": [
    { "id": "le-relief", "title": "Le relief de la Chine",
      "summary": "Les grands ensembles de relief : montagnes de l'ouest, plaines de l'est." },
    { "id": "le-climat", "title": "Le climat",
      "summary": "Les zones climatiques et la mousson, du nord aride au sud humide." },
    { "id": "la-population", "title": "La population",
      "summary": "Répartition, densités et grandes villes de la Chine." }
  ]
}

Cas document illisible :
{
  "error": "unreadable",
  "message": "Document difficile à lire (qualité ou écriture manuscrite). Réessaie avec un document plus net, un fichier texte, ou colle le contenu directement."
}

CONTRAINTES
- JSON valide uniquement.
- "id" = slug stable : minuscules, mots séparés par des tirets, sans accents ni
  espaces (ex. « la-population »).
- "summary" = une phrase courte et informative : elle aide l'enseignant à VALIDER
  le découpage, donc elle doit dire clairement ce que couvre la leçon.
- Respecte la langue du document pour les titres et résumés.

RAPPEL IMPORTANT SUR LE NOMBRE DE LEÇONS
Le nombre de leçons doit refléter le CONTENU RÉEL, jamais un minimum à atteindre.
S'il n'y a qu'un seul thème, renvoie UNE SEULE leçon dans le tableau "lessons".
Ne multiplie jamais les leçons par mimétisme de l'exemple ci-dessus : un document
court et mono-thème = une seule leçon, et c'est parfaitement correct.

DOCUMENT À STRUCTURER :
{content}
```

> **Note d'injection** : pour une entrée **texte**, le serveur remplace `{content}`
> par le texte extrait. Pour une entrée **visuelle** (PDF scanné/photo), le document
> est passé en **image(s)** à Claude et `{content}` est remplacé par une consigne du
> type « lis les images fournies ci-dessus » (même mécanisme que l'actuel
> `_call_claude`, cf. §2.4).

### 4.3 Notes d'intégration

- **Prompt nouveau** : il n'existe **pas** aujourd'hui (l'IA actuelle fait tout en un seul appel document = leçon).
- **Entrée via la vision de Claude** : texte **ou** visuel — **pas d'OCR séparé** (cf. §2.4).
- **Sortie → interface de validation enseignant** : l'objet `{ unit_title, subject, direction, lessons[] }` alimente l'écran où l'enseignant **renomme / réordonne / fusionne / supprime** les leçons. Le cas `{ error: "unreadable", … }` affiche le message et **bloque** le passage au Temps 2.
- **Après validation** : chaque leçon (`title` + `summary` + **la portion source correspondante**) est passée au **Prompt B** (Partie 2), un appel par leçon.

---

## SECTION 4 — Partie 2 : Le Prompt B « Professeur »

> **Décision d'architecture (fondée sur la recherche)** : le « Prompt B » n'est
> **pas un seul prompt monolithique**, mais **TROIS appels** groupés par
> interdépendance. Cette intro pose l'**orchestration** ; le **texte** des prompts
> B1, B2, B3 sera rédigé ensuite, **un par un**.

### 4.4 Pourquoi 3 appels (et pas 1 seul)

- Forcer un LLM à produire un **schéma JSON massif en un seul appel DÉGRADE son raisonnement (~10-15 %)** et provoque des **oublis de champs**. Règle de production établie : **un schéma par tâche** ; au-delà de **~50 champs**, découper en plusieurs appels.
- À l'inverse, **trop d'appels (6+)** crée de la **fragmentation** et un **coût de coordination** élevé. La **zone optimale** en production est **3-4 appels** groupés.
- Notre leçon = **beaucoup de structure** (concepts, 13 types de quiz, passes, story à 6 interactions, reading à 8 blocs, exam). **Trop pour 1 appel.**
- **Solution : 3 appels groupés par INTERDÉPENDANCE** — ce qui est lié reste ensemble, ce qui est autonome est isolé.

### 4.5 Les 3 appels

#### Appel B1 — « Noyau pédagogique »
- **Génère** : `concepts` + `quiz` (les 13 types) + `passes` + `exam`.
- **Pourquoi groupés** : tout est **lié par `concept_id`**. L'`exam` teste **les mêmes notions** que les quiz ; les générer **ensemble** garantit la **cohérence des notions** (mêmes concepts couverts, pas de dérive).
- **Entrée** : la **source de la leçon** (titre + résumé + portion source correspondante).
- **Sortie** : `{ concepts[], exam }`.

#### Appel B2 — « Lecture »
- **Génère** : `reading` (les 8 blocs + le glossaire `terms`).
- **Pourquoi séparé** : tâche **autonome** — **exposition** de contenu, **pas d'évaluation**. Isolé = **qualité rédactionnelle maximale** (le modèle se concentre sur expliquer clairement).
- **Entrée** : la **source de la leçon**.
- **Sortie** : `{ reading }`.

#### Appel B3 — « Histoire »
- **Génère** : `story` (`scene` + `characters` + les 6 interactions).
- **Pourquoi séparé** : tâche **créative** (narration, personnages, dialogue) **très différente** de la logique des quiz. Isolé = l'IA **se concentre sur le récit**.
- **Entrée** : la **source de la leçon** + **LA LISTE DES CONCEPTS produits par B1** — pour que la story **illustre les bons concepts** (via `concept_ref` sur ses steps).
- **Sortie** : `{ story }`.

### 4.6 Orchestration (côté serveur)

- **Ordre** : **B1 d'abord** (ses concepts sont une **entrée de B3**). Ensuite **B2 et B3 en PARALLÈLE** (indépendants entre eux).
- **Assemblage** : le serveur **fusionne les 3 sorties** dans l'**objet leçon final** (§3.1) :
  - `concepts[]` + `exam` ← **B1**
  - `reading` ← **B2**
  - `story` ← **B3**
  - **+ champs racine** (voir provenance ci-dessous).
- **Robustesse (fallback par bloc)** : si un appel échoue, on le **rejoue SEUL**, **sans refaire les autres**. Un échec de la story (B3) ne fait **pas** reperdre les concepts/exam déjà générés (B1). Chaque bloc est régénérable indépendamment.
- **Provenance des champs racine** (§3.1) :

| Champ racine | Source |
|---|---|
| `title` | **Prompt A** (Architecte) — titre de la leçon validé par l'enseignant |
| `subject` | **Prompt A** (Architecte) — matière + niveau détectés |
| `direction` | **Prompt A** (Architecte) — `ltr`/`rtl` détecté |
| `id` | **serveur** (slug de la leçon, issu de l'Architecte) |
| `color` | **B1** — couleur d'accent de la leçon (déduite de la matière) |
| `guide` | **B1** — nom du personnage fil rouge |

> Note : `color` et `guide` sont **complétés par B1** car ils relèvent de la
> mise en forme pédagogique de la leçon (cohérents avec la matière et la story),
> tandis que `title`/`subject`/`direction` viennent de l'étape Architecte déjà
> validée par l'enseignant.

#### Diagramme du flux

```
                 source de la leçon
                 (title + summary + portion source)
                          │
                          ▼
                  ┌───────────────┐
                  │  APPEL B1     │  « Noyau pédagogique »
                  │ concepts+quiz │
                  │ +passes+exam  │
                  └───────┬───────┘
                          │  { concepts[], exam }
            ┌─────────────┴───────────────┐
            │ (les concepts alimentent B3)│
            ▼                             ▼
   ┌─────────────────┐          ┌──────────────────┐
   │   APPEL B2      │   ∥      │    APPEL B3       │   (B2 ∥ B3 : en parallèle)
   │   « Lecture »   │          │   « Histoire »    │
   │   { reading }   │          │   { story }       │
   └────────┬────────┘          └────────┬──────────┘
            └───────────────┬────────────┘
                            ▼
                  ┌──────────────────────┐
                  │   ASSEMBLAGE serveur │
                  │  leçon finale (§3.1) │
                  │  B1+B2+B3 + racine   │
                  └──────────────────────┘
```

---

### 4.7 Prompt B1 — « Noyau pédagogique » (texte, partie 1/2)

> Texte **final** du Prompt B1, prêt à copier dans le code (`apps/lessons/services.py`,
> constante `NOYAU_PROMPT`). Les variables `{…}` sont injectées par le serveur.
>
> **Périmètre du Temps 1** : tout le corps du prompt **SAUF** le catalogue détaillé
> des 13 types de quiz, qui sera inséré au **Temps 2 (§4.8)** à l'emplacement
> marqué `[[CATALOGUE DES 13 TYPES — voir 4.8]]`.
>
> **Approche retenue** : **réflexion puis JSON** (`<reflexion>` puis `<json>`) —
> meilleure qualité pédagogique sur le noyau.

```text
Tu es un concepteur pédagogique malien expert, spécialiste de l'ÉVALUATION. Tu
connais le programme scolaire malien — du préscolaire au supérieur — ses matières
(français, maths, SVT, physique-chimie, histoire-géographie, anglais, philosophie,
informatique, droit, comptabilité, éducation islamique et fiqh en arabe) et tu
ancres tes exemples dans le quotidien malien (marché de Bamako, francs CFA, mangues,
transport, famille, champs, boutique, mosquée).

TA MISSION
Tu reçois la source d'UNE seule leçon (son titre, son résumé, et la portion de
document correspondante). Tu génères le NOYAU PÉDAGOGIQUE de cette leçon :
- les CONCEPTS,
- leurs QUIZ (selon les types autorisés ci-dessous),
- le découpage en PASSES,
- et l'EXAMEN.

Tu ne génères PAS le texte de lecture (« reading ») ni l'histoire (« story ») :
ils sont produits par d'autres appels. Concentre-toi uniquement sur le noyau.

APPROCHE EN 2 PHASES (obligatoire)
Tu réponds en deux blocs successifs et rien d'autre :

<reflexion>
Ici tu ANALYSES et PLANIFIES avant de produire le moindre JSON :
- identifie les concepts clés de la leçon (vise 3 à 6, selon la richesse réelle) ;
- repère les concepts RICHES qui méritent d'être découpés en plusieurs passes ;
- pour chaque concept, choisis les types de quiz qui le testent le mieux ;
- planifie ce que l'examen doit couvrir.
Ce bloc est un BROUILLON DE PLANIFICATION : écris-le librement, il sera IGNORÉ par
le serveur. Il sert uniquement à améliorer la qualité de ton JSON.
</reflexion>

<json>
Ici, et SEULEMENT ici, tu produis le JSON strict qui découle de ta réflexion.
Le serveur n'extrait QUE ce bloc.
</json>

PRINCIPES DE GÉNÉRATION DES CONCEPTS
- VOLUME ADAPTATIF : le nombre de concepts reflète la richesse RÉELLE du contenu.
  3 à 6 est une fourchette indicative, pas un quota : ne remplis jamais pour
  atteindre un minimum, ne tronque jamais une notion pour rester sous un maximum.
- Chaque concept = UNE idée maîtrisable, avec :
    "id"    : slug snake_case stable (ex. "transport_membranaire"),
    "name"  : nom lisible (ex. « Le transport membranaire »),
    "order" : position 1..N dans la leçon.
- 4 à 8 quiz par concept (indicatif, selon la richesse du concept).

DÉCOUPAGE EN PASSES
- Un concept avec PEU de quiz (moins de 8) → "passes": 1 (aucun découpage).
- Un concept RICHE → "passes": 2 à 4, par DIFFICULTÉ CROISSANTE ou par SOUS-THÈME.
- Chaque quiz porte un "pass_index" (0 = première passe, 1 = deuxième, etc.).
- Contraintes : 1 ≤ passes ≤ 4 ; tout pass_index est dans [0, passes-1] ; aucune
  passe ne doit être vide.

CHOIX DES TYPES DE QUIZ
- Choisis le type selon ce qui teste le MIEUX le concept — jamais pour « faire joli ».
- Privilégie une variété NATURELLE : tester un concept de plusieurs façons l'ancre
  mieux. Mais ne force pas la variété au détriment de la pertinence.
- N'utilise QUE les types décrits dans le catalogue ci-dessous.

[[CATALOGUE DES 13 TYPES — voir 4.8]]

- RAPPEL STRICT : n'utilise JAMAIS de type reporté (ceux dépendant d'image, d'audio,
  ou de correction par IA). Tu ne produis que les 13 types du catalogue ci-dessus.

GÉNÉRATION DE L'EXAMEN
- L'examen couvre les concepts de la leçon ; chaque question porte un "concept_id".
- Les questions sont GÉNÉRÉES SPÉCIFIQUEMENT pour l'examen : ne reprends PAS les
  quiz des concepts à l'identique. Reformule, teste les mêmes notions autrement —
  l'examen ÉVALUE, il ne fait pas réciter.
- "pass_mark" : 0.6 par défaut.
- "duration" : durée en secondes, environ 60 s par question.
- Les questions d'examen utilisent les mêmes types de quiz (catalogue ci-dessus).

CHAMPS color ET guide
Tu complètes deux champs de mise en forme de la leçon :
- "color" : une couleur d'accent (hex) cohérente avec la matière.
- "guide" : le nom d'un personnage fil rouge malien (ex. « Cyto », « Numa »). Ce
  même personnage pourra être réutilisé par l'histoire de la leçon.

FORMAT DE SORTIE (RÈGLE ABSOLUE)
- Exactement DEUX blocs, dans cet ordre : <reflexion>…</reflexion> puis <json>…</json>.
- Aucun texte hors de ces deux blocs. Aucun markdown.
- Le contenu de <json> est un objet JSON VALIDE et STRICT, de la forme :
{
  "color": "#10B981",
  "guide": "Cyto",
  "concepts": [
    {
      "id": "transport_membranaire",
      "name": "Le transport membranaire",
      "order": 3,
      "passes": 2,
      "quiz": [ /* questions, types du catalogue, chacune avec pass_index */ ]
    }
  ],
  "exam": {
    "pass_mark": 0.6,
    "duration": 600,
    "questions": [ /* questions taguées concept_id, types du catalogue */ ]
  }
}
- Le premier caractère du bloc <json> est { et le dernier est }.

LEÇON À TRAITER
Titre   : {lesson_title}
Résumé  : {lesson_summary}
Source  :
{lesson_source}
```

---

### 4.8 Prompt B1 — Catalogue des 13 types (texte, partie 2/2)

> Bloc à **insérer dans `NOYAU_PROMPT`** (§4.7) **à la place exacte** du marqueur
> `[[CATALOGUE DES 13 TYPES — voir 4.8]]`.
> Ce sont des **instructions de génération** (comment produire chaque type),
> alignées **trait pour trait** sur les schémas de la **§3 — Partie 2** (mêmes
> tokens, mêmes noms de champs).

```text
LES 13 TYPES DE QUIZ AUTORISÉS

Voici les 13 SEULS types de quiz que tu peux générer. Pour chacun : son token
exact (champ "type"), les champs à produire, quand l'utiliser et le piège à
éviter. N'invente aucun autre type.

Champs communs à CHAQUE quiz : "id" (identifiant court), "type" (un des 13 tokens),
"instruction" (l'énoncé affiché à l'élève), le payload propre au type, et un
"explanation" optionnel (texte affiché après la réponse — recommandé quand
l'erreur est instructive).

POINT DE VIGILANCE — pass_index vs concept_id :
- un quiz placé DANS un concept ("concepts[].quiz[]") porte "pass_index" (le
  numéro de sa passe, 0-based) ;
- une question d'EXAMEN ("exam.questions[]") porte "concept_id" (la notion testée)
  et JAMAIS de "pass_index".

────────────────────────────────────────────────────────────────────────────
1. mcq_single — QCM à réponse unique
- Quand l'utiliser : une question avec UNE seule bonne réponse (toutes matières).
- Champs : "options" (liste de textes), "answer_index" (index de la bonne option).
- Exemple :
  { "type": "mcq_single", "instruction": "Quelle est la capitale du Mali ?",
    "options": ["Bamako", "Ouagadougou", "Dakar", "Niamey"], "answer_index": 0,
    "explanation": "Bamako est la capitale du Mali depuis 1908." }
- Piège : s'il y a plusieurs bonnes réponses, utilise mcq_multiple. "answer_index"
  doit bien pointer la bonne option.

────────────────────────────────────────────────────────────────────────────
2. mcq_multiple — QCM à réponses multiples
- Quand l'utiliser : plusieurs bonnes réponses à cocher (au moins 2).
- Champs : "options" (liste), "answer_indices" (liste des index corrects).
- Exemple :
  { "type": "mcq_multiple", "instruction": "Lesquelles de ces villes sont au Mali ?",
    "options": ["Ségou", "Abidjan", "Sikasso", "Mopti"], "answer_indices": [0, 2, 3],
    "explanation": "Abidjan est en Côte d'Ivoire." }
- Piège : prévois AU MOINS 2 bonnes réponses (sinon mcq_single). L'élève est jugé
  sur l'ensemble EXACT (ni oubli ni excès).

────────────────────────────────────────────────────────────────────────────
3. true_false — Vrai / Faux
- Quand l'utiliser : une affirmation franchement vraie ou fausse.
- Champs : "answer" (booléen true ou false).
- Exemple :
  { "type": "true_false", "instruction": "Le fleuve Niger traverse le Mali.",
    "answer": true, "explanation": "Le Niger traverse le Mali sur près de 1 700 km." }
- Piège : l'affirmation doit être NETTE, jamais ambiguë ou « ça dépend ».

────────────────────────────────────────────────────────────────────────────
4. k_prime — Grille Vrai/Faux (type K')
- Quand l'utiliser : tester plusieurs micro-affirmations liées à un même thème.
- Champs : "statements" = liste d'objets { "text", "answer" (booléen) }.
- Exemple :
  { "type": "k_prime", "instruction": "Pour chaque affirmation, indique Vrai ou Faux :",
    "statements": [
      { "text": "La mitochondrie produit l'énergie.", "answer": true },
      { "text": "Le noyau contient l'ADN.", "answer": true },
      { "text": "La membrane laisse tout passer.", "answer": false } ],
    "explanation": "La membrane est sélective." }
- Piège : 3 à 5 affirmations INDÉPENDANTES, chacune avec son propre "answer".
  L'élève doit avoir TOUTES les lignes justes.

────────────────────────────────────────────────────────────────────────────
5. cloze_test — Texte à trous
- Quand l'utiliser : compléter des mots-clés dans une phrase (langues, définitions).
- Champs : "text" avec des trous notés {{0}}, {{1}}… ; "answers" = liste, answers[i]
  étant la réponse du trou i.
- Exemple :
  { "type": "cloze_test", "instruction": "Complète le texte :",
    "text": "La photosynthèse produit du {{0}} et de l'{{1}}.",
    "answers": ["glucose", "oxygène"] }
- Piège : numérote les trous sans saut (0,1,2…) ; "answers" dans le MÊME ordre ;
  réponses courtes (1 à 3 mots), comparées en ignorant accents/casse.

────────────────────────────────────────────────────────────────────────────
6. matching — Appariement
- Quand l'utiliser : relier deux colonnes (organe→fonction, mot→traduction, date→événement).
- Champs : "pairs" = liste d'objets { "left", "right" } dans l'ordre CORRECT.
- Exemple :
  { "type": "matching", "instruction": "Associe chaque organe à sa fonction :",
    "pairs": [
      { "left": "Cœur", "right": "Pompe le sang" },
      { "left": "Poumon", "right": "Échange les gaz" },
      { "left": "Rein", "right": "Filtre le sang" } ] }
- Piège : donne les paires DANS LE BON APPARIEMENT (le frontend mélange l'affichage).
  Chaque "left" a un seul "right" ; 3 à 5 paires ; pas de doublon.

────────────────────────────────────────────────────────────────────────────
7. chrono_order — Remise en ordre
- Quand l'utiliser : remettre des étapes/événements en séquence (histoire, procédés).
- Champs : "items" (liste de textes, affichés mélangés) ; "correct_order" = liste
  des INDEX de "items" dans l'ordre attendu.
- Exemple :
  { "type": "chrono_order", "instruction": "Remets ces événements dans l'ordre :",
    "items": ["Indépendance du Mali", "Empire du Mali (Soundiata)", "Colonisation française"],
    "correct_order": [1, 2, 0] }
- Piège : "correct_order" contient des INDEX de "items", pas les textes eux-mêmes.

────────────────────────────────────────────────────────────────────────────
8. number_input — Réponse numérique
- Quand l'utiliser : une réponse chiffrée exacte (dénombrement, calcul simple).
- Champs : "answer" (nombre) ; "tolerance" (optionnel, écart accepté, défaut 0).
- Exemple :
  { "type": "number_input", "instruction": "Combien de régions le Mali compte-t-il (2023) ?",
    "answer": 19, "tolerance": 0 }
- Piège : "answer" est un nombre PUR (pas de texte ni d'unité). Mets une "tolerance"
  pour les résultats décimaux ou les mesures.

────────────────────────────────────────────────────────────────────────────
9. dynamic_formula — Formule à variables aléatoires
- Quand l'utiliser : un calcul paramétré, RÉGÉNÉRÉ par élève (anti-triche) — maths,
  physique, comptabilité.
- Champs : "formula_template" (l'équation, ex. "a*x + b = c") ; "variables" (un objet
  où chaque variable a { "min", "max", "step" }) ; "solution_formula" (la formule qui
  CALCULE la réponse à partir des variables) ; "expected_input" ("numeric") ;
  "correct_answer" (valeur témoin d'un tirage).
- Exemple :
  { "type": "dynamic_formula", "instruction": "Résous a·x + b = c pour x.",
    "formula_template": "a*x + b = c",
    "variables": { "a": {"min":2,"max":9,"step":1}, "b": {"min":1,"max":20,"step":1},
                   "c": {"min":21,"max":60,"step":1} },
    "solution_formula": "(c - b) / a", "expected_input": "numeric", "correct_answer": 4 }
- Piège : "solution_formula" DOIT être une vraie formule CALCULABLE à partir des
  variables (ex. "(c - b) / a"), jamais une constante. Choisis des "min"/"max"/"step"
  qui donnent un résultat propre. Le serveur recalcule la réponse par élève.

────────────────────────────────────────────────────────────────────────────
10. math_expression — Expression mathématique
- Quand l'utiliser : produire/transformer une expression algébrique (développer, factoriser).
- Champs : "correct_expression" (forme de référence) ; "accepted_equivalents" (liste
  de formes équivalentes acceptées).
- Exemple :
  { "type": "math_expression", "instruction": "Développe (x + 1)².",
    "correct_expression": "x^2 + 2*x + 1",
    "accepted_equivalents": ["x**2+2x+1", "1 + 2x + x^2"] }
- Piège : fournis TOUJOURS quelques "accepted_equivalents" (ordre des termes, ^ vs **)
  pour aider la comparaison. Évite les expressions trop ouvertes à interprétation.

────────────────────────────────────────────────────────────────────────────
11. spot_the_bug — Trouver le bug
- Quand l'utiliser : identifier la ligne fautive d'un extrait de code (informatique).
- Champs : "language" ; "code" (liste de lignes) ; "buggy_line" (index 0-based de la
  ligne erronée) ; "correct_fix" (optionnel, la correction, affichée en explication).
- Exemple :
  { "type": "spot_the_bug", "instruction": "Quelle ligne contient l'erreur ?",
    "language": "python",
    "code": ["def moyenne(notes):", "    total = 0", "    for n in notes:",
             "        total = n", "    return total / len(notes)"],
    "buggy_line": 3, "correct_fix": "total += n" }
- Piège : UNE seule ligne fautive, clairement identifiable ; "buggy_line" est un
  index 0-based dans "code".

────────────────────────────────────────────────────────────────────────────
12. parsons_puzzle — Puzzle de code (Parsons)
- Quand l'utiliser : reconstituer un code en ORDRE et INDENTATION (programmation).
- Champs : "language" ; "lines" = liste de { "id", "text", "correct_indent" (niveau,
  0 = sans indentation) } ; "correct_sequence" = liste des "id" dans l'ordre correct.
- Exemple :
  { "type": "parsons_puzzle", "instruction": "Remets ce code Python dans l'ordre :",
    "language": "python",
    "lines": [
      { "id": "L1", "text": "def carre(x):", "correct_indent": 0 },
      { "id": "L2", "text": "return x * x", "correct_indent": 1 },
      { "id": "L3", "text": "print(carre(5))", "correct_indent": 0 } ],
    "correct_sequence": ["L1", "L2", "L3"] }
- Piège : "correct_sequence" liste des "id" (pas des textes) ; "correct_indent"
  cohérent avec la syntaxe. Réservé au code.

────────────────────────────────────────────────────────────────────────────
13. odd_one_out — L'intrus
- Quand l'utiliser : trouver l'élément qui n'appartient pas à un groupe.
- Champs : "items" (liste de textes) ; "odd_index" (index 0-based de l'intrus).
- Exemple :
  { "type": "odd_one_out", "instruction": "Quel mot est l'intrus ?",
    "items": ["Bambara", "Peul", "Songhaï", "Wolof"], "odd_index": 3,
    "explanation": "Le wolof est surtout parlé au Sénégal, pas au Mali." }
- Piège : UN seul intrus, avec un critère commun clair aux autres items ;
  "odd_index" est 0-based.

────────────────────────────────────────────────────────────────────────────

Tu utilises CES 13 TYPES UNIQUEMENT — jamais les types reportés (image, audio,
correction par IA, etc.).
```

> **Cohérence vérifiée** : tokens et noms de champs **identiques** à la §3 — Partie 2
> (`mcq_single/answer_index`, `mcq_multiple/answer_indices`, `true_false/answer`,
> `k_prime/statements{text,answer}`, `cloze_test/text+answers`, `matching/pairs{left,right}`,
> `chrono_order/items+correct_order`, `number_input/answer+tolerance`,
> `dynamic_formula/formula_template+variables+solution_formula+expected_input+correct_answer`,
> `math_expression/correct_expression+accepted_equivalents`,
> `spot_the_bug/language+code+buggy_line+correct_fix`,
> `parsons_puzzle/language+lines{id,text,correct_indent}+correct_sequence`,
> `odd_one_out/items+odd_index`). **Aucune divergence introduite.**

---

### 4.9 Prompt B2 — « Lecture » (texte)

> Texte **final** du Prompt B2, prêt à copier dans le code (`apps/lessons/services.py`,
> constante `LECTURE_PROMPT`). Les variables `{…}` sont injectées par le serveur.
>
> **Approche retenue** : **JSON direct** (pas de phase `<reflexion>`). La lecture
> est de l'**exposition** — le gain d'une réflexion préalable serait marginal ;
> on la réserve à B1 (raisonnement d'évaluation).

```text
Tu es un concepteur pédagogique malien expert, spécialiste de la RÉDACTION
pédagogique claire. Tu écris pour des élèves maliens qui lisent sur un téléphone :
phrases nettes, ton chaleureux, exemples du quotidien malien (marché de Bamako,
francs CFA, mangues, transport, famille, champs, boutique, mosquée).

TA MISSION
Tu reçois la source d'UNE seule leçon (son titre, son résumé, et la portion de
document correspondante). Tu génères UNIQUEMENT le CONTENU DE LECTURE de cette
leçon (le champ « reading ») : un texte structuré, clair et agréable à lire sur
mobile.

Tu ne génères PAS les quiz, ni l'histoire, ni l'examen : ils sont produits par
d'autres appels. Concentre-toi sur la lecture.

STRUCTURE À PRODUIRE
- "title"     : le titre de la lecture.
- "direction" : le sens de lecture, fourni ci-dessous ({direction}) — « ltr » ou « rtl ».
- "terms"     : un glossaire { mot: définition }. Chaque mot devient cliquable dans
                le texte ; définitions COURTES.
- "sections"  : une liste de sections, chacune { "id", "title", "blocks" }.

LES 8 TYPES DE BLOCS (champ "type" de chaque bloc)
- "p"       : paragraphe — { "text", "simple"? }.  "simple" est OPTIONNEL : une
              reformulation plus simple, à n'ajouter QUE si le paragraphe est difficile.
- "def"     : définition — { "term", "text" }.
- "callout" : encart — { "icon", "label", "text" } (ex. label « Le saviez-vous »).
- "key"     : points clés — { "items": [ ... ] } (liste de phrases courtes).
- "example" : exemple concret — { "text" }.
- "reflect" : invite à réfléchir — { "prompt" } (une question ouverte, sans réponse).
- "warn"    : mise en garde — { "text" } (piège fréquent, confusion à éviter).
- "check"   : mini-quiz DANS la lecture — { "variant", "question", ..., "explanation" } :
                • variant "tf"  : ajoute "answer" (booléen true/false) ;
                • variant "qcm" : ajoute "options" (liste) et "answer" (index de la
                  bonne option).
              "explanation" justifie la bonne réponse.

PRINCIPES DE RÉDACTION
- Sois clair et progressif ; adapte le vocabulaire au niveau détecté dans la source.
- ALTERNE les types de blocs pour rythmer la lecture — jamais 10 paragraphes
  d'affilée. Entrelace définitions, exemples, points clés, encarts, vérifications.
- Glossaire "terms" : inclus les mots techniques importants, avec des définitions
  brèves et accessibles.
- Version "simple" d'un "p" : seulement quand le paragraphe est DIFFICILE, pas
  systématiquement.
- Insère QUELQUES blocs "check" répartis dans la lecture, pour vérifier la
  compréhension en cours de route.
- Ancre les explications dans le quotidien malien quand c'est pertinent.

FORMAT DE SORTIE (RÈGLE ABSOLUE)
- Tu réponds UNIQUEMENT avec un objet JSON valide. Aucun texte avant, aucun texte
  après, aucun bloc markdown. Le premier caractère est { et le dernier est }.
- Forme exacte :
{
  "reading": {
    "title": "La membrane plasmique",
    "direction": "ltr",
    "terms": {
      "membrane plasmique": "La fine enveloppe qui entoure la cellule et contrôle ce qui entre et sort.",
      "transport actif": "Le passage d'une molécule à travers la membrane qui consomme de l'énergie (ATP)."
    },
    "sections": [
      {
        "id": "s1",
        "title": "La frontière de la cellule",
        "blocks": [
          { "type": "p", "text": "Chaque cellule est entourée d'une membrane plasmique…",
            "simple": "Chaque cellule a une membrane autour d'elle." },
          { "type": "def", "term": "membrane plasmique", "text": "la fine enveloppe qui entoure la cellule." },
          { "type": "callout", "icon": "spark", "label": "Le saviez-vous",
            "text": "La membrane est si fine qu'il en faudrait des milliers pour égaler une feuille de papier." },
          { "type": "check", "variant": "tf",
            "question": "La membrane laisse tout passer sans distinction.",
            "answer": false, "explanation": "Elle est sélective : elle choisit ce qui passe." }
        ]
      },
      {
        "id": "s2",
        "title": "Comment les choses entrent ?",
        "blocks": [
          { "type": "key", "items": ["L'eau passe par osmose.", "Le glucose passe par une protéine."] },
          { "type": "example", "text": "Le glucose, trop gros, utilise une protéine de transport." },
          { "type": "warn", "text": "Ne confonds pas osmose (sans énergie) et transport actif (avec énergie)." },
          { "type": "reflect", "prompt": "Pourquoi une barrière sélective plutôt qu'un mur fermé ?" },
          { "type": "check", "variant": "qcm",
            "question": "Qu'est-ce qui fait passer le glucose ?",
            "options": ["La bicouche seule", "Une protéine de transport", "Rien"],
            "answer": 1, "explanation": "Le glucose est trop gros : il passe par une protéine." }
        ]
      }
    ]
  }
}

LEÇON À TRAITER
Sens de lecture : {direction}
Titre   : {lesson_title}
Résumé  : {lesson_summary}
Source  :
{lesson_source}
```

> **Cohérence vérifiée** : les 8 blocs et leurs champs sont **identiques** à la
> §3.5 (`p{text,simple?}`, `def{term,text}`, `callout{icon,label,text}`,
> `key{items[]}`, `example{text}`, `reflect{prompt}`, `warn{text}`,
> `check{variant,question,(options/answer),explanation}`) — le `check` utilise bien
> `answer` booléen en `tf` et `answer` index en `qcm`, et `explanation` (pas
> `explain`). **Aucune divergence introduite.**

---

### 4.10 Prompt B3 — « Histoire » (texte)

> Texte **final** du Prompt B3, prêt à copier dans le code (`apps/lessons/services.py`,
> constante `HISTOIRE_PROMPT`). Les variables `{…}` sont injectées par le serveur.
>
> **Approche retenue** : **JSON direct** (pas de phase `<reflexion>`) — tâche
> créative, sans raisonnement d'évaluation à planifier ; la réflexion est réservée à B1.
>
> **Subtilité clé** : B3 reçoit en entrée, **en plus de la source**, les **CONCEPTS**
> et le **GUIDE** produits par **B1** — pour que l'histoire illustre les vrais
> concepts et réutilise le personnage fil rouge.

```text
Tu es un concepteur pédagogique malien expert, spécialiste de la NARRATION
pédagogique : tu RACONTES pour faire comprendre. Tu crées des personnages
attachants et des situations du quotidien malien (marché de Bamako, francs CFA,
mangues, transport, famille, champs, boutique, mosquée).

TA MISSION
Tu reçois la source d'UNE leçon, la LISTE DES CONCEPTS de cette leçon, et le nom
du personnage GUIDE. Tu génères UNE histoire interactive (le champ « story ») qui
fait VIVRE les notions de la leçon : l'élève comprend en agissant, pas en regardant.

Tu ne génères PAS les quiz, ni le texte de lecture, ni l'examen : ils sont produits
par d'autres appels. Concentre-toi sur l'histoire.

COHÉRENCE AVEC LE RESTE DE LA LEÇON (important)
- Réutilise le personnage GUIDE fourni ({guide}) comme personnage CENTRAL de
  l'histoire (il fait partie de "characters").
- L'histoire doit ILLUSTRER les concepts fournis ci-dessous. Sur les steps qui
  testent ou mettent en scène une notion précise, ajoute un champ optionnel
  "concept_ref" portant l'"id" du concept concerné (issu de la liste fournie).

STRUCTURE À PRODUIRE
- "scene"      : { "name", "c1", "c2" } — nom de la scène + 2 couleurs d'ambiance (hex).
- "characters" : liste d'objets { "id", "name", "role", "color", "side" }
                 ("side" vaut "left" ou "right" ; "color" en hex ; le GUIDE en fait partie).
- "steps"      : la liste du déroulé, composée des 6 types ci-dessous.

LES 6 TYPES DE STEP (champ "type")
- "narration" : { "text" } — décor/atmosphère, SANS personnage.
- "npc"       : { "who", "text" } — réplique d'un personnage ("who" = "id" d'un character).
- "choice"    : { "prompt", "options": [ { "label", "correct", "reply" } ] } — choix
                narratif. UNE option a "correct": true ; "reply" est la réponse du
                personnage à chaque option.
- "input"     : { "prompt", "answers": [ ... ], "hint", "ok" } — saisie libre.
                "answers" = réponses acceptées (comparées en ignorant accents/casse) ;
                "hint" = indice ; "ok" = message quand c'est juste.
- "tokens"    : { "prompt", "tokens": [ ... ], "solution": [ ... ], "ok" } — remettre
                des éléments dans l'ordre. "solution" = les "tokens" dans le bon ordre.
- "blank"     : { "prompt", "parts": [ ... ], "options": [ ... ], "answer", "ok" } —
                compléter une phrase à trou. "parts" encadre le trou (avant/après) ;
                "answer" est la bonne option.
Tout step peut porter, en plus, un "concept_ref" optionnel (id d'un concept).

PRINCIPES NARRATIFS
- Écris une VRAIE petite histoire avec un fil : début, péripétie, résolution — pas
  une suite de questions déguisées.
- 2 à 3 personnages maximum, dont le GUIDE.
- ALTERNE narration / dialogue / interactions pour rythmer.
- Les interactions testent la compréhension des concepts EN SITUATION.
- Ancre l'histoire dans le quotidien malien (lieux, noms, objets).
- Ton chaleureux, adapté au niveau détecté dans la source.

FORMAT DE SORTIE (RÈGLE ABSOLUE)
- Tu réponds UNIQUEMENT avec un objet JSON valide. Aucun texte avant, aucun texte
  après, aucun bloc markdown. Le premier caractère est { et le dernier est }.
- Forme exacte :
{
  "story": {
    "scene": { "name": "Au marché de Bamako", "c1": "#F97316", "c2": "#BE123C" },
    "characters": [
      { "id": "awa",  "name": "Awa",   "role": "Guide",    "color": "#F97316", "side": "left" },
      { "id": "moussa","name": "Moussa","role": "Vendeur",  "color": "#22D3EE", "side": "right" }
    ],
    "steps": [
      { "type": "narration", "text": "Marché de Bamako, au lever du jour. Awa accompagne son petit frère faire les courses." },
      { "type": "npc", "who": "awa", "text": "Bonjour Moussa ! Trois mangues, s'il te plaît." },
      { "type": "npc", "who": "moussa", "text": "Chaque mangue coûte 150 francs. Voyons le total…" },
      { "type": "input", "prompt": "Combien coûtent 3 mangues à 150 F l'unité ?",
        "answers": ["450", "450 f", "450 francs"], "hint": "150 × 3.",
        "ok": "450 francs, exact !", "concept_ref": "multiplication" },
      { "type": "choice", "prompt": "Awa paie avec 500 F. Que doit rendre Moussa ?", "options": [
          { "label": "50 francs", "correct": true,  "reply": "Oui : 500 − 450 = 50 F." },
          { "label": "150 francs", "correct": false, "reply": "Non, ça c'est le prix d'une mangue." }
        ], "concept_ref": "soustraction" },
      { "type": "npc", "who": "moussa", "text": "Voilà tes 3 mangues et 50 francs. À bientôt !" }
    ]
  }
}

ENTRÉES
Guide (personnage central) : {guide}
Concepts à illustrer (id — name) :
{concepts_list}
Titre   : {lesson_title}
Résumé  : {lesson_summary}
Source  :
{lesson_source}
```

> **Cohérence vérifiée** : structure et 6 types **identiques** à la §3.6 —
> `scene{name,c1,c2}`, `characters{id,name,role,color,side}`, et les steps
> `narration{text}`, `npc{who,text}`, `choice{prompt,options[{label,correct,reply}]}`,
> `input{prompt,answers[],hint,ok}`, `tokens{prompt,tokens[],solution[],ok}`,
> `blank{prompt,parts[],options[],answer,ok}` + `concept_ref` optionnel (cohérent
> avec §3.4, qui s'appuie dessus pour placer les nodes story). **Aucune divergence
> introduite.**

---

<!-- SECTION 4 COMPLÈTE (Architecte + orchestration + B1 + B2 + B3). -->

## SECTION 5 — TYPES DE QUIZ FUTURS (reportés)

> **But de cette section** : documenter ce qui **n'est PAS** dans les 13 types
> actifs (Section 3 — Partie 2), afin que :
> 1. le **Prompt B** sache **ne jamais générer** ces types ;
> 2. on puisse les **reprendre plus tard** sans refaire la réflexion.

**Préambule — contrainte qui a écarté ces types.** Un type est reporté pour
**au moins une** de ces raisons :
- **Dépendance image/audio** — notre IA génère du **texte pur**, **pas** d'images ni de son (cf. contrainte stricte Section 3).
- **Complexité frontend** trop lourde pour la v2 (composant interactif coûteux à construire, surtout mobile + connexion lente).
- **Coût/latence de correction** — un type qui appelle l'IA à **chaque soumission** (≠ les 13 types instantanés).

> ⛔ **Règle pour le Prompt B** : ces types **ne doivent JAMAIS** être produits
> tant qu'ils ne sont pas **explicitement réactivés** dans cette section (déplacés
> en Section 3 — Partie 2). Le prompt doit lister ces tokens comme **interdits**.

Les schémas JSON ci-dessous sont des **esquisses pressenties** (pour gagner du
temps plus tard) — **non définitifs**, non normatifs.

---

### 5.1 Vague 2 — sans image/audio, mais frontend lourd

Ces types respectent la contrainte « texte pur » mais demandent un **composant
interactif conséquent**. À débloquer quand l'effort frontend est justifié.

#### `graph_plot` — placer un/des point(s) sur un graphe
- **Ce qu'il fait** : l'élève place un ou plusieurs points sur un graphe à axes (ex. tracer le point (3 ; 5), ou les points d'une fonction affine).
- **Pourquoi reporté** : exige un **composant SVG interactif** (clic précis sur coordonnées, snap à la grille, validation de position, tolérance) — gros chantier, délicat sur mobile + connexion lente.
- **Condition de déblocage** : un **composant graphe interactif réutilisable** (axes, grille, placement de points, lecture des coordonnées).
- **Esquisse JSON**
```jsonc
{ "type": "graph_plot",
  "instruction": "Place le point A(3 ; 5).",
  "axes": { "x": { "min": -5, "max": 5 }, "y": { "min": -5, "max": 5 } },
  "expected_points": [ { "x": 3, "y": 5 } ],
  "tolerance": 0.25 }
```

#### `code_fill_blanks` — compléter des trous DANS du code
- **Ce qu'il fait** : compléter des trous **au sein d'un extrait de code** (≠ `cloze_test` : ici comptent la **syntaxe** et l'**indentation**).
- **Pourquoi reporté** : nécessite un **éditeur de code inline** + une **validation syntaxique** (pas une simple égalité de chaîne).
- **Condition de déblocage** : composant d'édition de code (coloration, trous typés) + validateur tolérant aux espaces/syntaxe.
- **Esquisse JSON**
```jsonc
{ "type": "code_fill_blanks",
  "instruction": "Complète la fonction.",
  "language": "python",
  "code_template": "def carre(x):\n    return x {{0}} x",
  "answers": ["*"] }
```

#### `predict_output` — prédire la sortie d'un code
- **Ce qu'il fait** : l'élève **prédit ce qu'affiche** un extrait de code.
- **Pourquoi reporté** : exige **soit** une **exécution sandbox** (sécurité, infra), **soit** une **sortie figée** parfaitement fiable (risque d'ambiguïté si l'IA se trompe sur la sortie).
- **Condition de déblocage** : sandbox d'exécution sûre **ou** processus de validation fiable de la sortie attendue.
- **Esquisse JSON**
```jsonc
{ "type": "predict_output",
  "instruction": "Qu'affiche ce programme ?",
  "language": "python",
  "code": ["x = 2", "y = 3", "print(x * y)"],
  "expected_output": "6" }
```

---

### 5.2 Vague 3 — nécessitent un système d'images/audio

> **Bloqueur commun** : **l'absence d'un système de médias**. L'IA **ne génère
> ni images ni son**. **Déblocage commun** (l'un des trois) : (a) **upload média
> par l'enseignant**, (b) **banque d'images** — ⚠️ **attention droits d'auteur au
> Mali**, (c) **TTS navigateur** pour l'audio (la synthèse vocale est déjà
> disponible côté client).

#### `image_labeling` — étiqueter les zones d'un schéma
- **Ce qu'il fait** : associer des étiquettes aux zones d'un schéma (ex. parties d'une cellule, d'une fleur).
- **Dépendance média** : une **image de schéma** + des **zones définies** (coordonnées).
- **Esquisse JSON**
```jsonc
{ "type": "image_labeling",
  "instruction": "Étiquette les parties de la cellule.",
  "image_ref": "media://schema-cellule.png",
  "zones": [ { "x": 120, "y": 80, "label": "Noyau" }, { "x": 200, "y": 140, "label": "Membrane" } ] }
```

#### `hotspot` — cliquer une zone précise d'une image
- **Ce qu'il fait** : cliquer le **bon endroit** d'une image (carte du Mali, schéma anatomique).
- **Dépendance média** : une **image** + une **zone-cible** (rectangle/cercle).
- **Esquisse JSON**
```jsonc
{ "type": "hotspot",
  "instruction": "Clique sur la région de Tombouctou.",
  "image_ref": "media://carte-mali.png",
  "target": { "shape": "circle", "x": 310, "y": 90, "r": 40 } }
```

#### `audio_to_text` — dictée (écouter → taper)
- **Ce qu'il fait** : l'élève **écoute** un énoncé et **tape** ce qu'il entend (dictée, orthographe, langues).
- **Dépendance média** : **audio** — réalisable via **TTS navigateur** (déblocage le plus simple de la Vague 3).
- **Esquisse JSON**
```jsonc
{ "type": "audio_to_text",
  "instruction": "Écoute et écris la phrase.",
  "audio_text": "Le Niger est un grand fleuve.",
  "answer": "Le Niger est un grand fleuve." }
```
> Note : `audio_text` peut être **lu par le TTS** (pas besoin de fichier son), ce qui rend ce type **débloquable en premier** dans la Vague 3.

#### `audio_visual_match` — son → bonne image (maternelle)
- **Ce qu'il fait** : entendre un son/mot et **cliquer la bonne image** (préscolaire, lecture).
- **Dépendance média** : **audio** (TTS possible) **+ images** des choix (vrai bloqueur).
- **Esquisse JSON**
```jsonc
{ "type": "audio_visual_match",
  "instruction": "Écoute et clique la bonne image.",
  "audio_text": "chat",
  "options": [ { "image_ref": "media://chat.png", "correct": true },
               { "image_ref": "media://chien.png", "correct": false } ] }
```

#### `tracing_quiz` — tracer lettres/chiffres au doigt
- **Ce qu'il fait** : tracer une lettre ou un chiffre **au doigt** (préscolaire, graphisme).
- **Dépendance/difficulté** : un **moteur de tracé tactile** (capture du geste, comparaison de forme) — **très spécifique**, à part des autres.
- **Esquisse JSON**
```jsonc
{ "type": "tracing_quiz",
  "instruction": "Trace la lettre A.",
  "glyph": "A",
  "stroke_paths": [ "M0,100 L50,0 L100,100", "M25,50 L75,50" ] }
```

---

### 5.3 À décider plus tard — `ai_graded_essay`

- **Ce qu'il fait** : réponse **libre/rédigée**, **corrigée par l'IA**.
- **Le problème de fond** : l'IA intervient à **chaque soumission élève** (≠ génération **unique** de la leçon). Conséquences :
  - **Coût** : 500 élèves = **500+ appels IA** (vs 0 pour les 13 types).
  - **Latence** : **3-5 s** sur connexion lente au Mali (vs correction **instantanée** des 13 types).
- **Trois options en présence** :
  - **A) Vraie correction IA** — intelligente, fine ; **coûteuse et lente**. À réserver **lycée/université**.
  - **B) `keyword_essay`** — vérifier des **mots-clés** côté serveur : **instantané, gratuit**, mais **moins fin**.
  - **C) Hybride** — `keyword` **par défaut**, correction **IA en option payante**.
- **Esquisse JSON (option B, la plus proche d'instantané)**
```jsonc
{ "type": "keyword_essay",
  "instruction": "Explique pourquoi le Niger est vital pour le Mali.",
  "required_keywords": ["eau", "agriculture", "pêche", "transport"],
  "min_keywords": 3 }
```
- **Statut** : ⛔ **DÉCISION EXPLICITEMENT REPORTÉE**. **Ne pas implémenter** tant que l'option (A/B/C) n'est pas tranchée. Le Prompt B ne génère **ni** `ai_graded_essay` **ni** `keyword_essay` pour l'instant.

---

## SECTION 6 — PHASES D'EXÉCUTION

> **Préambule — l'ordre A → B → C est CONTRAINT, pas un choix.** Il découle des
> dépendances : le **frontend** (C) a besoin des **modèles** (B) ; les **modèles**
> se testent avec des données réalistes que seul le **format IA** (A) sait
> produire. On ne peut donc pas paralléliser ces phases — A débloque B, B débloque
> C. C'est une **nécessité technique**.

```
   PHASE A          PHASE B            PHASE C
  Format IA   →   Modèles & migr.  →  Frontend
 (produit les     (stockent les       (affiche les
  données)         données A)          données B)
```

---

### PHASE A — FORMAT IA (détaillée)

**But** : implémenter **toute la chaîne de génération** spécifiée en Section 4.
Chaque étape a un **critère de validation testable**.

#### A.1 — Prompt A « Architecte » (`services.py`)
- Coder `ARCHITECT_PROMPT` (§4.2) + la fonction d'appel.
- Gérer l'entrée **texte ET visuelle** (vision Claude, §2.4 — pas d'OCR séparé).
- Garde-fou **document illisible** → `{ "error": "unreadable", … }`.
- **✅ Validation** : uploader un PDF → obtenir un JSON `{ unit_title, subject, direction, lessons[] }` valide.

> **Point de validation de structure** : entre l'Architecte (A.1) et le Prompt B1
> (A.2), la structure proposée doit être validée (renommer/réordonner/fusionner/
> supprimer les leçons). Pendant la Phase A, cette validation est **MANUELLE** (on
> édite le JSON de structure à la main pour tester le pipeline). L'**INTERFACE**
> réelle de validation enseignant se construit en **Phase C** (c'est du frontend).
> Le flux complet en 2 temps reste décrit en §2.2.

#### A.2 — Prompt B1 « Noyau » (`services.py`)
- Coder `NOYAU_PROMPT` (corps §4.7 + catalogue §4.8).
- **Parsing** : extraire le bloc `<json>` (**ignorer** `<reflexion>`), valider le schéma (`concepts`, `quiz`, `passes`, `exam`).
- Valider les **invariants des passes** (§3.3 : `1 ≤ passes ≤ 4`, `pass_index ∈ [0, passes-1]`, aucune passe vide).
- **✅ Validation** : générer le noyau d'une leçon ; vérifier que les **13 types** peuvent apparaître et sont structurellement valides.

#### A.3 — Prompts B2 « Lecture » et B3 « Histoire »
- Coder `LECTURE_PROMPT` (§4.9) et `HISTOIRE_PROMPT` (§4.10).
- **B3 reçoit** les `concepts` + le `guide` produits par B1.
- **✅ Validation** : `reading` (8 blocs) et `story` (6 interactions) valides et cohérents (guide réutilisé, `concept_ref` pointant des concepts réels).

#### A.4 — Orchestration des 3 appels (§4.6)
- **B1 d'abord**, puis **B2 ∥ B3** (parallèle), puis **assemblage** de la leçon finale (§3.1).
- **Fallback par bloc** : rejouer un appel échoué **seul**, sans refaire les autres.
- **✅ Validation** : une **leçon complète** assemblée depuis un vrai document.

#### A.5 — Évaluation des 13 types (`evaluate_answer`)
- Implémenter la règle d'évaluation de **chaque type** (§3 — Partie 2) : égalité, **ensemble exact** (mcq_multiple, k_prime), **normalisation** (cloze_test), **séquence** (chrono_order, parsons), **tolérance** (number_input), **symbolique** (math_expression), **anti-triche** (dynamic_formula : tirage + recalcul serveur), etc.
- **✅ Validation** : chaque type évalué correctement (juste/faux) **côté serveur**.

#### A.6 — Jalon final Phase A
- **✅ Validation** : un **document réel → une leçon v2 complète, valide, évaluable**. Le format IA tourne **de bout en bout**.

---

### PHASE B — MODÈLES & MIGRATIONS (synthétique)

> Esquisse — **à détailler le moment venu** (réflexion propre avant de coder).

- **Champs leçon** nouveaux : `reading_data`, `exam_data`, `color`, `guide`, `direction`.
- **Nouveau modèle UNITÉ** au-dessus de la leçon (**1 document = 1 unité** ; porte ouverte au multi-document plus tard, cf. §2.1).
- **Nouveau modèle `ExamAttempt`** (sur le modèle de `StoryAttempt`).
- **Progression des passes** : champs pour `pass_index` / `passesDone`.
- **Migrations additives** + **régénération du seed**.
- **Dépendance** : a besoin du **format A** pour produire des données de test réalistes.

---

### PHASE C — FRONTEND (synthétique)

> Esquisse — **à détailler le moment venu**.

- **Interface de validation enseignant** (Temps 1 du flux §2.2) : afficher la
  structure proposée par l'Architecte, permettre **renommer / réordonner /
  fusionner / supprimer** les leçons, **confirmer** pour lancer le Temps 2. Le cas
  `error: unreadable` affiche le message et **bloque**.
- **Traduire le design React → HTML/HTMX/Alpine/Tailwind**, écran par écran :
  parcours (nodes + passes + anneaux) → lecture (TTS, glossaire, `check`) → story
  (6 interactions) → quiz → exam (`ExamPlayer`) → profil.
- **Un composant de rendu PAR type de quiz (13)**, dans l'esthétique du design
  (rappel **1.6** : le design ne couvre que le MCQ → tout le reste est à créer).
- Les **3 thèmes** (dark / light / comfort).
- **Dépendance** : a besoin des **modèles B** et du **format A**.

---

## SECTION 7 — DÉCISIONS TRANCHÉES & EN ATTENTE

> **Nature de cette section** : un **récapitulatif** (pas de spec nouvelle). Un
> index des décisions prises dans le document + celles laissées en attente, pour
> retrouver vite « quoi + pourquoi » sans tout relire. Chaque ligne renvoie à sa
> section.

### 7.1 Décisions tranchées (figées)

| Décision | Pourquoi (condensé) | Réf. |
|---|---|---|
| Hiérarchie à 2 niveaux : unité → leçon → concept → quiz | Structure claire ; la leçon reste plate (design) | §2.1 |
| 1 document = 1 unité maintenant ; multi-document plus tard | Simplicité v1, porte ouverte sans la construire | §2.1 |
| Flux d'ingestion en 2 temps (structure → validation → contenu) | Gros docs, context window, contrôle humain avant génération lourde | §2.2 |
| Vision native de Claude, **pas d'OCR séparé** ; accepte PDF scanné/photo imprimés | Moins de code, plus robuste sur les scans | §2.4 |
| Vidéo/audio **exclus** ; manuscrit **déconseillé** | Claude ne traite ni vidéo ni audio ; OCR cursive peu fiable | §2.4 |
| `reading_data` **séparé** ; champ `direction` (rtl arabe) dès maintenant | Lecture autonome ; support fiqh anticipé | §3.1, §3.5 |
| **Nodes assemblés par le SERVEUR**, pas par l'IA | L'IA fournit la matière ; le serveur orchestre le parcours | §1.4, §3.4 |
| Volume **adaptatif** (pas de quota rigide) | Refléter la richesse réelle, ni remplir ni tronquer | §1.5 |
| **13 types** de quiz actifs, **texte pur**, évaluation **100 % serveur** | Couverture multi-matières, instantané, gratuit | §3 P2 |
| `short_answer` **abandonné** ; `ai_graded_essay` **reporté** | Redondant / coût-latence de correction IA | §3 P2, §5.3 |
| Champ `explanation` **optionnel commun** aux 13 types | Feedback pédagogique uniforme | §3 P2 |
| `date` du reading **supprimée** | L'IA n'a pas à inventer une date ; sans valeur | §3.5, §4.9 |
| Prompt B = **3 appels** (B1 noyau, B2 lecture, B3 histoire) | Zone optimale 3-4 ; éviter la dégradation du méga-JSON | §4.4-4.6 |
| B1 **réflexion-puis-JSON** ; B2/B3 **JSON direct** | Réflexion utile au raisonnement d'évaluation, marginale sur l'exposition/le récit | §4.7, §4.9, §4.10 |
| `color`/`guide` générés par **B1** ; `title`/`subject`/`direction` par l'**Architecte** | Mise en forme pédagogique côté B1 ; détection côté A | §4.6 |
| Questions d'examen **générées spécifiquement** (pas de rejeu des quiz) | L'examen évalue, ne fait pas réciter | §3.7, §4.7 |
| Design React = **référence visuelle à reconstruire** ; ne couvre que le MCQ → à étendre aux 13 types | Style fourni, pas la couverture fonctionnelle | §1.6 |
| Ordre d'exécution **A → B → C contraint** par dépendances | Format débloque modèles, modèles débloquent frontend | §6 |
| Interface de validation enseignant = **Phase C** (frontend), pas Phase A | Phase A purement backend, testable sans écran | §6 |

### 7.2 Décisions en attente (à trancher plus tard)

| Question ouverte | Options connues | Réf. |
|---|---|---|
| `ai_graded_essay` | A) vraie correction IA · B) `keyword_essay` (serveur) · C) hybride | §5.3 |
| Multi-document par unité | quand l'activer + comment agréger plusieurs documents | §2.1 |
| Types reportés **Vague 2** (`graph_plot`, `code_fill_blanks`, `predict_output`) | quand les activer (chacun = un composant/infra à construire) | §5.1 |
| Types reportés **Vague 3** (image/audio) | déblocage commun : upload média · banque d'images · TTS | §5.2 |
| Déploiement | hébergeur, domaine, stockage média, email — **non décidés** (hors périmètre spec, à planifier) | — |

---

*Le `PORTAL_V2_SPEC.md` est la **source de vérité vivante** de la refonte v2 :
toute nouvelle décision v2 doit y être reflétée.*



