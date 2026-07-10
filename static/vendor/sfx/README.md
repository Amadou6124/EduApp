# SFX — sons du portail élève (Histoire / Quiz / Examen)

Le module partagé `static/js/learn-sfx.js` joue ces fichiers s'ils existent,
**sinon il retombe** sur des sons synthétisés (Web Audio). Tout fonctionne donc
même sans fichiers (bips de secours).

## Fichiers livrés (générés, présents ICI)

| Fichier         | Quand il joue                                | Son                                   |
|-----------------|----------------------------------------------|---------------------------------------|
| `correct.wav`   | Bonne réponse                                | carillon 2 notes montantes            |
| `wrong.wav`     | Mauvaise réponse                             | descente **douce** (jamais punitif)   |
| `combo.wav`     | La flamme s'allume (2 bonnes d'affilée)      | arpège rapide + étincelle             |
| `complete.wav`  | Fin de série / histoire / examen             | petit jingle majeur                   |
| `perfect.wav`   | Série **parfaite** (3 étoiles)               | fanfare + accord tenu vibré           |
| `tap.wav`       | Envoi d'une réponse / interaction            | pop court                             |

- Format : **wav** (lu nativement par tous les navigateurs). Mono 44.1 kHz,
  léger (≈ 8–75 Ko). Volume baissé côté code (0.5), sons doux façon Duolingo.
- **Régénérer / retoucher** : `gen_sfx.py` (ici même ; pur stdlib Python,
  aucun outil externe) — ajuster notes, timbre (partiels), décroissance, gain,
  puis `python3 static/vendor/sfx/gen_sfx.py static/vendor/sfx/`.

## Remplacer par des sons « pro » (optionnel)
Déposer ici des fichiers du **même nom** (`correct/wrong/complete/tap`). Si tu
prends du `.mp3`, adapter l'extension dans `learn-sfx.js` (`n + '.wav'`).
Sources libres : freesound.org (CC0), pixabay.com/sound-effects, mixkit.co.

## Production (statiques hashés)
Le module reçoit sa base via `LearnSFX.init("/static/vendor/sfx/")`. Avec un
pipeline de hash, passer par des URLs `{% static %}` pour prendre le hash en compte.
