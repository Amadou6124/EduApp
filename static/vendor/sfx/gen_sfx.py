"""Générateur des sons du portail élève — pur stdlib (wave/math/struct).

Design sonore « Ludique doux » : timbres ronds (sinus + harmoniques douces),
attaque courte, décroissance naturelle, écho discret — jamais agressif, jamais
punitif. Regénérer :  python3 static/vendor/sfx/gen_sfx.py static/vendor/sfx/

| Fichier        | Quand                                   | Caractère                    |
|----------------|------------------------------------------|------------------------------|
| tap.wav        | interaction / envoi                      | pop très court               |
| correct.wav    | bonne réponse                            | carillon 2 notes montantes   |
| wrong.wav      | mauvaise réponse                         | descente douce (pas de buzz) |
| combo.wav      | la flamme s'allume (2 bonnes d'affilée)  | arpège rapide + étincelle    |
| complete.wav   | fin de série / histoire / examen         | petit jingle                 |
| perfect.wav    | série PARFAITE (3 étoiles)               | fanfare + accord tenu vibré  |
"""
import math
import struct
import sys
import wave

SR = 44100


def synth(notes, *, gain=0.5, echo_ms=90, echo_mix=0.16, tail=0.25):
    """notes = [(freq_hz|list, start_s, dur_s, vol, glide_hz)] → échantillons float."""
    end = max(s + d for _, s, d, _, _ in notes) + tail
    n = int(end * SR)
    buf = [0.0] * n
    for freq, start, dur, vol, glide in notes:
        freqs = freq if isinstance(freq, (list, tuple)) else [freq]
        i0, ns = int(start * SR), int(dur * SR)
        for k in range(ns):
            t = k / SR
            env = min(1.0, t / 0.004) * math.exp(-3.2 * t / dur)   # attaque 4 ms, décrois. exp
            s = 0.0
            for f0 in freqs:
                f = f0 + (glide * (t / dur))
                ph = 2 * math.pi * f * t
                # timbre « carillon rond » : fondamentale + 2 harmoniques discrètes
                s += (math.sin(ph) + 0.28 * math.sin(2 * ph) + 0.10 * math.sin(3 * ph))
            buf[i0 + k] += (s / len(freqs)) * env * vol
    # écho discret (une seule répétition, douce)
    if echo_mix > 0:
        d = int(echo_ms / 1000 * SR)
        for i in range(n - 1, d - 1, -1):
            buf[i] += buf[i - d] * echo_mix
    # normalisation à -2 dB + fondu de fin
    peak = max(1e-9, max(abs(x) for x in buf))
    norm = (10 ** (-2 / 20)) / peak * gain / 0.5
    fade = int(0.04 * SR)
    for i in range(n):
        g = norm * (min(1.0, (n - i) / fade) if i > n - fade else 1.0)
        buf[i] = max(-1.0, min(1.0, buf[i] * g))
    return buf


def write_wav(path, samples):
    with wave.open(path, 'w') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b''.join(struct.pack('<h', int(x * 32767)) for x in samples))


# ── notes (Hz) ────────────────────────────────────────────────────────────────
A3, F3 = 220.00, 174.61
C5, E5, G5 = 523.25, 659.25, 783.99
A5, C6, Cs6, E6, G6, A6 = 880.00, 1046.50, 1108.73, 1318.51, 1567.98, 1760.00

SOUNDS = {
    # pop court, discret (glissando descendant très rapide)
    'tap':      dict(notes=[(1150, 0, 0.05, 0.5, -320)], gain=0.30, echo_mix=0, tail=0.05),
    # carillon 2 notes montantes — la récompense de base
    'correct':  dict(notes=[(E6, 0, 0.16, 0.8, 0), (A6, 0.09, 0.24, 0.9, 0)], gain=0.5),
    # descente douce et ronde — l'erreur n'est jamais une punition
    'wrong':    dict(notes=[(A3, 0, 0.16, 0.9, -18), (F3, 0.11, 0.22, 0.8, -12)],
                     gain=0.42, echo_mix=0.08),
    # la flamme s'allume : arpège rapide + étincelle à l'octave
    'combo':    dict(notes=[(A5, 0, 0.09, 0.75, 0), (Cs6, 0.07, 0.09, 0.8, 0),
                            (E6, 0.14, 0.12, 0.85, 0), (A6, 0.22, 0.20, 0.7, 0)], gain=0.5),
    # fin de série : petit jingle majeur
    'complete': dict(notes=[(C5, 0, 0.12, 0.8, 0), (E5, 0.10, 0.12, 0.8, 0),
                            (G5, 0.20, 0.12, 0.85, 0), ([C6, E6], 0.31, 0.42, 0.9, 0)],
                     gain=0.52, tail=0.35),
    # série PARFAITE : fanfare + accord final tenu, léger vibrato (glide subtil)
    'perfect':  dict(notes=[(C5, 0, 0.11, 0.8, 0), (G5, 0.09, 0.11, 0.8, 0),
                            (C6, 0.18, 0.11, 0.85, 0), (E6, 0.27, 0.11, 0.85, 0),
                            (G6, 0.36, 0.14, 0.9, 0),
                            ([C6, E6, G6], 0.50, 0.75, 0.95, 4)],
                     gain=0.55, echo_mix=0.20, tail=0.5),
}

if __name__ == '__main__':
    out = (sys.argv[1] if len(sys.argv) > 1 else '.').rstrip('/')
    for name, spec in SOUNDS.items():
        write_wav(f'{out}/{name}.wav', synth(**spec))
        print(f'  {name}.wav écrit')
