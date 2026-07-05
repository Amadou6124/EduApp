#!/usr/bin/env python3
"""Génère 4 SFX WAV agréables (carillon doux) pour le portail élève.
Pur stdlib (wave/struct/math) — aucun outil externe.
Sortie : static/vendor/sfx/{tap,correct,wrong,complete}.wav
"""
import wave, struct, math, os

SR = 44100


def blank(dur):
    return [0.0] * int(SR * dur)


def add_tone(buf, freq, start, dur, gain=0.5, partials=(1.0, 0.5, 0.25, 0.12),
             decay=6.0, attack=0.006, detune=0.0):
    """Additionne une note « cloche » : somme de partiels harmoniques, attaque
    rapide + décroissance exponentielle. Les partiels aigus décroissent + vite."""
    n0 = int(SR * start)
    n = int(SR * dur)
    for i in range(n):
        t = i / SR
        # enveloppe : attaque linéaire puis décroissance exp
        if t < attack:
            env = t / attack
        else:
            env = math.exp(-(t - attack) * decay)
        s = 0.0
        for k, amp in enumerate(partials, start=1):
            # partiels aigus un peu plus courts (plus « métallique/doux »)
            pa = amp * math.exp(-(t) * decay * 0.15 * (k - 1))
            f = freq * k + detune * k
            s += pa * math.sin(2 * math.pi * f * t)
        idx = n0 + i
        if idx < len(buf):
            buf[idx] += s * env * gain


def normalize(buf, peak=0.72):
    m = max(1e-9, max(abs(x) for x in buf))
    g = peak / m
    return [x * g for x in buf]


def fade_edges(buf, ms=6):
    n = int(SR * ms / 1000)
    for i in range(min(n, len(buf))):
        buf[i] *= i / n
        buf[-1 - i] *= i / n
    return buf


def write_wav(path, buf):
    buf = fade_edges(normalize(buf))
    with wave.open(path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        frames = b''.join(struct.pack('<h', int(max(-1, min(1, x)) * 32767)) for x in buf)
        w.writeframes(frames)
    print('écrit', os.path.basename(path), len(buf) / SR, 's')


# Notes (tempérament égal, A4=440)
def note(n):  # n = demi-tons depuis A4
    return 440.0 * (2 ** (n / 12.0))

C5, E5, G5, C6 = note(3), note(7), note(10), note(15)
E5b, B5 = note(7), note(14)
E4, B3 = note(-5), note(-10)


def gen(target_dir):
    # tap — clic doux court, sinus quasi pur, décroissance très rapide
    b = blank(0.09)
    add_tone(b, note(12), 0, 0.09, gain=0.5, partials=(1.0, 0.35), decay=42, attack=0.002)
    write_wav(os.path.join(target_dir, 'tap.wav'), b)

    # correct — deux notes montantes brillantes (quinte), carillon
    b = blank(0.42)
    add_tone(b, E5, 0.00, 0.34, gain=0.5, partials=(1.0, 0.55, 0.28, 0.14), decay=6.5)
    add_tone(b, B5, 0.09, 0.36, gain=0.5, partials=(1.0, 0.5, 0.25, 0.12), decay=6.0)
    write_wav(os.path.join(target_dir, 'correct.wav'), b)

    # wrong — deux notes descendantes DOUCES (pas punitif), timbre chaud
    b = blank(0.34)
    add_tone(b, E4, 0.00, 0.26, gain=0.5, partials=(1.0, 0.4, 0.12), decay=9.0, detune=0.6)
    add_tone(b, B3, 0.10, 0.26, gain=0.5, partials=(1.0, 0.4, 0.12), decay=9.0, detune=0.6)
    write_wav(os.path.join(target_dir, 'wrong.wav'), b)

    # complete — petite fanfare arpège ascendant (accord majeur + octave)
    b = blank(0.85)
    for j, f in enumerate((C5, E5, G5, C6)):
        add_tone(b, f, j * 0.10, 0.55, gain=0.42,
                 partials=(1.0, 0.55, 0.30, 0.16, 0.08), decay=4.5)
    # petite « brillance » finale sur l'octave
    add_tone(b, C6, 0.42, 0.42, gain=0.22, partials=(1.0, 0.6, 0.35), decay=5.0)
    write_wav(os.path.join(target_dir, 'complete.wav'), b)


if __name__ == '__main__':
    import sys
    d = sys.argv[1]
    gen(d)
