# SFX — sons de l'Histoire (portail élève)

Le lecteur d'histoire (`templates/student_learning/story_v2.html`) joue ces sons
s'ils existent, **sinon il retombe** sur des sons synthétisés (Web Audio). Donc
tant que ces fichiers ne sont pas là, tout fonctionne (avec les bips de secours).

## Fichiers attendus (à déposer ICI, self-hostés)

| Fichier          | Quand il joue                          | Durée idéale |
|------------------|----------------------------------------|--------------|
| `correct.mp3`    | Bonne réponse                          | ~0.3–0.6 s   |
| `wrong.mp3`      | Mauvaise réponse                       | ~0.3–0.5 s   |
| `complete.mp3`   | Fin de l'histoire (récompense)         | ~0.8–1.5 s   |
| `tap.mp3`        | Envoi d'une réponse / interaction      | ~0.1–0.2 s   |

- Format : **mp3** (compatible partout). Garder **léger** (quelques Ko chacun).
- Volume déjà baissé côté code (0.5) ; des sons **doux et courts** (façon
  Duolingo / Nintendo), pas agressifs.

## Où trouver des sons libres de droits
- **freesound.org** (filtrer par licence CC0), **pixabay.com/sound-effects**
  (libre), **mixkit.co/free-sound-effects** (UI / game).
- Chercher : « correct answer », « success chime », « error / wrong buzz »,
  « pop / tap UI », « level complete jingle ».

## Une fois les fichiers ajoutés
En **production** (statiques hashés), remplacer dans `story_v2.html` la base
`sfxBase` par des `{% static 'vendor/sfx/correct.mp3' %}` (etc.) pour que le
hash de fichier soit pris en compte. En dev/démo, la base actuelle suffit.
