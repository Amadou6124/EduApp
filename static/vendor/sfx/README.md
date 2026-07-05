# SFX — sons du portail élève (Histoire / Quiz / Examen)

Le module partagé `static/js/learn-sfx.js` joue ces fichiers s'ils existent,
**sinon il retombe** sur des sons synthétisés (Web Audio). Tout fonctionne donc
même sans fichiers (bips de secours).

## Fichiers livrés (générés, présents ICI)

| Fichier         | Quand il joue                      | Son                                   |
|-----------------|------------------------------------|---------------------------------------|
| `correct.wav`   | Bonne réponse                      | deux notes montantes (carillon doux)  |
| `wrong.wav`     | Mauvaise réponse                   | deux notes descendantes **douces**    |
| `complete.wav`  | Fin d'histoire / examen (récompense)| petite fanfare arpège majeur          |
| `tap.wav`       | Envoi d'une réponse / interaction  | clic court                            |

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
