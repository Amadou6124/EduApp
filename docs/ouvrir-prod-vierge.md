# Ouvrir une prod vierge — la fiche recette

**À quoi sert cette fiche :** le jour où tu ouvres l'app pour une **vraie** école,
suis ces étapes **dans l'ordre**. Rien à retenir par cœur — tu ouvres ce fichier et
tu copies-colles les commandes.

## L'idée en deux lignes

- **Ton ordinateur (démo)** = le classeur avec les fausses données (Groupe SyDev, élèves
  inventés). Il **reste chez toi**, il ne part jamais en ligne.
- **Le site en ligne (prod)** = un classeur **vierge**, que la vraie école remplit elle-même.

Le code a été vérifié : il ne fabrique **aucune** fausse donnée tout seul. Une prod neuve
reste donc réellement propre. *(Les commandes `seed_demo…` ne créent des fausses données
que si TU les lances — ne les lance jamais en prod.)*

---

## Les 4 étapes

### 1. Préparer le classeur vide
Une fois l'hébergeur branché sur sa base Postgres (variable `DATABASE_URL` définie), le
script de déploiement `build.sh` fait déjà tout le travail :

```bash
./build.sh
```

Ça installe les dépendances, **crée le schéma vide** (`migrate`), la table du cache
(`createcachetable`) et prépare les fichiers statiques. → base propre, rien dedans.

> Sur Render, `build.sh` tourne automatiquement à chaque déploiement (« Build Command »).

### 2. Créer ton compte super-admin (le grand chef)
Dans le terminal du serveur (sur Render : onglet **Shell** du service) :

```bash
python manage.py createsuperuser
```

On te demandera :
- **Numéro de téléphone** (ton identifiant de connexion)
- **Nom complet**
- **Mot de passe** (un vrai mot de passe solide — jamais `test123`)

### 3. Créer la 1ʳᵉ vraie école + son directeur
- Va sur **`https://ton-domaine/superadmin/`**
- Connecte-toi avec le compte de l'étape 2
- Crée l'**école** réelle, puis le compte de son **directeur** (vrai numéro, vrai mot de passe)

### 4. Le directeur prend le relais
Le directeur se connecte et fait son installation, dans cet ordre :

> année scolaire → classes → périodes → frais → matières → matières × classes →
> enseignants → élèves

*(C'est le parcours du guide d'onboarding directeur.)*

---

## Ce qui reste chez toi (jamais en prod)

- L'école de démo **Groupe SyDev** et tous ses élèves/notes/paiements fictifs.
- Les commandes `seed_demo_finance`, `seed_demo`, `seed_demo_school_life`,
  `seed_demo_vacataires` — utiles **en local** pour t'entraîner ou faire une démo, jamais en prod.

---

## Si tu veux une démo « propre » en local aussi

Ta base locale est un **Postgres** nommé `eduapp` (voir `DB_NAME` dans ton `.env`).
Pour repartir d'une base vide **sur ton ordinateur** (par ex. avant de filmer une démo nette) :

```bash
# ⚠️ efface TOUTES tes données locales — à faire seulement en local
dropdb eduapp && createdb eduapp     # remplace eduapp par ton DB_NAME si tu l'as changé
python manage.py migrate             # recrée le schéma vide + données de référence
python manage.py createsuperuser
```

Puis tu re-remplis avec les `seed_demo…` si tu veux des données d'exemple.

> Variante plus douce (garde le schéma, vide juste les données) : `python manage.py flush`.
> Note : `flush` efface aussi les catégories de dépenses de référence ; `dropdb/createdb`
> les remet car il rejoue les migrations.
