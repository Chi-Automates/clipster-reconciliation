"""Synthesises the music bed + sound effects for the FBC advert (original audio, no samples)."""
import sys
import numpy as np
from scipy.signal import butter, lfilter
import wave

SR = 48000
DUR = 66.0
N = int(SR * DUR)
rng = np.random.default_rng(7)
BEAT = 0.5

L = np.zeros(N)
R = np.zeros(N)
SFX_L = np.zeros(N)
SFX_R = np.zeros(N)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def add(bufs, t, sig, gain=1.0, pan=0.0):
    i = int(t * SR)
    if i >= N or i < 0:
        return
    sig = sig[: N - i]
    bufs[0][i : i + len(sig)] += sig * gain * np.sqrt((1 - pan) / 2) * 1.414
    bufs[1][i : i + len(sig)] += sig * gain * np.sqrt((1 + pan) / 2) * 1.414


def filt(x, fc, kind="low", order=2):
    b, a = butter(order, np.array(fc) / (SR / 2), kind)
    return lfilter(b, a, x)


def env_t(d):
    return np.arange(int(d * SR)) / SR


# ---------- instruments ----------
def kick():
    t = env_t(0.32)
    f = 48 + 110 * np.exp(-t * 38)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 11) + 0.25 * np.exp(-t * 300) * rng.standard_normal(len(t))


def clap(soft=False):
    t = env_t(0.22)
    n = filt(rng.standard_normal(len(t)), [900, 5200], "band")
    e = np.exp(-t * 26)
    for d in (0.0, 0.011, 0.022):
        e += 0.6 * np.exp(-np.maximum(t - d, 0) * 90) * (t >= d)
    return n * e * (0.35 if soft else 0.6)


def hat(open_=False):
    t = env_t(0.16 if open_ else 0.05)
    n = filt(rng.standard_normal(len(t)), 7500, "high")
    return n * np.exp(-t * (22 if open_ else 85)) * 0.3


def snare():
    t = env_t(0.12)
    n = filt(rng.standard_normal(len(t)), [1200, 7000], "band")
    return (n * 0.5 + 0.3 * np.sin(2 * np.pi * 190 * t)) * np.exp(-t * 34)


def pluck(m, d=0.28, bright=1.0):
    t = env_t(d)
    f = mtof(m)
    s = np.zeros(len(t))
    for k in range(1, 7):
        s += np.sin(2 * np.pi * f * k * t) / k * np.exp(-t * (9 + 5 * k / bright))
    a = np.minimum(t / 0.004, 1)
    return s * a * 0.32


def bass(m, d):
    t = env_t(d)
    f = mtof(m)
    s = np.sin(2 * np.pi * f * t) + 0.45 * np.sin(2 * np.pi * 2 * f * t) + 0.2 * np.sin(2 * np.pi * 3 * f * t)
    e = np.minimum(t / 0.008, 1) * np.exp(-t * 3.5) * np.minimum((d - t) / 0.02, 1)
    return np.tanh(s * 1.4) * e * 0.5


def bell(m, d):
    t = env_t(d + 0.5)
    f = mtof(m)
    s = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 7) + 0.18 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t * 12)
    e = np.minimum(t / 0.006, 1) * np.exp(-t * (2.2 / max(d, 0.4) + 2.2))
    return s * e * 0.3


def pad(notes, d):
    t = env_t(d)
    s = np.zeros(len(t))
    for m in notes:
        f = mtof(m)
        for det in (-0.004, 0.0, 0.004):
            ph = 2 * np.pi * f * (1 + det) * t + rng.uniform(0, 6.28)
            s += np.sin(ph) + 0.33 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)
    e = np.minimum(t / 0.12, 1) * np.minimum((d - t) / 0.2, 1)
    return filt(s, 2200) * e * 0.03


def riser(d, f0=300, f1=7000):
    t = env_t(d)
    n = rng.standard_normal(len(t))
    out = np.zeros(len(t))
    # sweep a band-pass in chunks
    ch = 1024
    for i in range(0, len(t), ch):
        p = i / len(t)
        fc = f0 * (f1 / f0) ** p
        seg = n[max(0, i - ch) : i + ch]
        y = filt(seg, [fc * 0.7, min(fc * 1.4, SR / 2 - 100)], "band")
        out[i : i + ch] = y[-min(ch, len(t) - i) - (0 if i + ch <= len(t) else 0) :][: len(out[i : i + ch])]
    return out * (t / d) ** 2 * 0.5


def crash():
    t = env_t(2.2)
    n = filt(rng.standard_normal(len(t)), 4500, "high")
    return n * np.exp(-t * 2.4) * 0.3


# ---------- SFX ----------
def sfx_whoosh(d=0.5, lo=400, hi=5000):
    t = env_t(d)
    n = rng.standard_normal(len(t))
    y = filt(n, [lo, hi], "band")
    e = np.sin(np.pi * t / d) ** 2
    return y * e * 0.5


def sfx_pop(f=520):
    t = env_t(0.12)
    fr = f * (1 + 1.2 * np.exp(-t * 60))
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t * 38) * 0.6


def sfx_click():
    t = env_t(0.03)
    return (np.sin(2 * np.pi * 2400 * t) + 0.5 * rng.standard_normal(len(t))) * np.exp(-t * 220) * 0.4


def sfx_ding():
    t = env_t(0.9)
    s = np.zeros(len(t))
    for f, dl in ((1318.5, 0.0), (1760.0, 0.11)):
        tt = np.maximum(t - dl, 0)
        s += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 7) * (t >= dl)
    return s * 0.3


def sfx_chime(notes=(72, 76, 79, 84)):
    t = env_t(1.8)
    s = np.zeros(len(t))
    for i, m in enumerate(notes):
        dl = i * 0.07
        tt = np.maximum(t - dl, 0)
        f = mtof(m)
        s += (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2.76 * f * tt) * np.exp(-tt * 9)) * np.exp(-tt * 3.2) * (t >= dl)
    return s * 0.16


def sfx_sparkle(d=1.3):
    t = env_t(d)
    s = np.zeros(len(t))
    for _ in range(22):
        dl = rng.uniform(0, d * 0.7)
        f = rng.choice([2093, 2637, 3136, 3520, 4186, 5274])
        tt = np.maximum(t - dl, 0)
        s += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 18) * (t >= dl) * rng.uniform(0.4, 1)
    return s * 0.09


def sfx_impact():
    t = env_t(1.4)
    f = 42 + 60 * np.exp(-t * 18)
    lowb = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.5)
    n = filt(rng.standard_normal(len(t)), 1800) * np.exp(-t * 7) * 0.25
    return (lowb + n) * 0.6


def sfx_typing(d=1.1):
    out = np.zeros(int(d * SR))
    t = 0.0
    while t < d - 0.05:
        c = sfx_click() * rng.uniform(0.35, 0.7)
        c = filt(c, 3500)
        i = int(t * SR)
        out[i : i + len(c)] += c[: len(out) - i]
        t += rng.uniform(0.07, 0.15)
    return out


# ---------- arrangement ----------
CH = {
    "C": dict(tones=[60, 64, 67], bass=36, pad=[48, 55, 60, 64]),
    "G": dict(tones=[59, 62, 67], bass=43, pad=[43, 55, 59, 62]),
    "Am": dict(tones=[57, 60, 64], bass=45, pad=[45, 52, 57, 60]),
    "F": dict(tones=[57, 60, 65], bass=41, pad=[41, 53, 57, 60]),
}
CYCLE = ["C", "G", "Am", "F"]
LEAD = {
    "C": [(0, 1, 76), (1, 0.5, 79), (1.5, 1, 81), (2.5, 1.5, 79)],
    "G": [(0, 1, 74), (1, 0.5, 79), (1.5, 1, 83), (2.5, 1.5, 79)],
    "Am": [(0, 1, 76), (1, 0.5, 81), (1.5, 1, 84), (2.5, 1.5, 81)],
    "F": [(0, 1, 77), (1, 0.5, 81), (1.5, 1, 79), (2.5, 1.5, 76)],
}
M = (L, R)

# bars: (start, beats, chord, flags)
bars = []


def section(t0, nbars, flags, fill_beats=0, start_idx=0):
    t = t0
    for i in range(nbars):
        bars.append((t, 4, CYCLE[(start_idx + i) % 4], flags))
        t += 4 * BEAT
    if fill_beats:
        bars.append((t, fill_beats, "G", "fill"))
        t += fill_beats * BEAT
    return t


t = section(0.0, 4, "kick hat pluck pad")                 # 0-8   scene 1
t = section(t, 3, "kick hat pluck pad bass clapsoft", 2)   # 8-15  scene 2 (+fill)
t = section(t, 4, "kick hat16 pluck pad bass clap lead", 2)  # 15-24 scene 3
t = section(t, 4, "kick hat pluck pad bass clap")          # 24-32 scene 4
t = section(t, 4, "kick hat16 pluck pad bass clap lead")   # 32-40 scene 5
bars.append((40.0, 4, "F", "build"))                       # 40-42 demo day build
bars.append((42.0, 4, "C", "kick hat16 pluck pad bass clap lead crash"))  # 42-44 I MADE THIS
t = section(44.0, 4, "kick hat pluck pad bass clapsoft", 0, 1)  # 44-52 scene 7/8
t = section(t, 5, "kick hat16 pluck pad bass clap lead", 0, 1)  # 52-62 scene 8 + end card
assert abs(t - 62.0) < 1e-6

for (t0, nb, chn, fl) in bars:
    c = CH[chn]
    d = nb * BEAT
    if fl == "fill":
        add(M, t0, pad(c["pad"], d), 1.0)
        for k in range(nb * 4):
            add(M, t0 + k * BEAT / 4, snare(), 0.25 + 0.5 * k / (nb * 4))
        add(M, t0, riser(d), 0.5)
        continue
    if fl == "build":
        add(M, t0, pad(c["pad"], d - 0.3), 1.2)
        # accelerating snare roll, stops 0.3 s before the hit (the "pause")
        tt, step, k = 0.0, 0.25, 0
        while tt < d - 0.32:
            add(M, t0 + tt, snare(), 0.25 + 0.5 * tt / d)
            if tt > 1.0:
                step = 0.125
            tt += step
            k += 1
        add(M, t0, riser(d - 0.28), 0.7)
        for b in range(2):
            add(M, t0 + b * BEAT, kick(), 0.8)
        continue
    add(M, t0, pad(c["pad"], d + 0.05), 1.0)
    if "crash" in fl:
        add(M, t0, crash(), 1.0)
    for b in range(nb):
        tb = t0 + b * BEAT
        if "kick" in fl:
            add(M, tb, kick(), 0.9)
        if b % 2 == 1:
            if "clapsoft" in fl:
                add(M, tb, clap(True), 0.8)
            elif "clap" in fl:
                add(M, tb, clap(), 0.8)
        # hats
        if "hat16" in fl:
            for k in range(4):
                add(M, tb + k * BEAT / 4, hat(k == 2), 0.55 if k == 2 else 0.3, 0.2)
        elif "hat" in fl:
            add(M, tb + BEAT / 2, hat(True), 0.45, 0.2)
        # bass on off-beats (pumping feel)
        if "bass" in fl:
            add(M, tb + BEAT / 2, bass(c["bass"], BEAT * 0.45), 0.9)
            if b == 3:
                add(M, tb + BEAT * 0.75, bass(c["bass"] + 12, BEAT * 0.2), 0.5)
        # pluck arp in 8ths with ping-pong echo
        if "pluck" in fl:
            tn = c["tones"]
            pat = [tn[0], tn[1], tn[2], tn[0] + 12, tn[2], tn[1], tn[2], tn[0] + 12]
            for k in range(2):
                m = pat[(b * 2 + k) % 8] + 12
                tp = tb + k * BEAT / 2
                pan = -0.45 if (b * 2 + k) % 2 == 0 else 0.45
                add(M, tp, pluck(m), 0.55, pan)
                add(M, tp + BEAT * 0.75, pluck(m), 0.2, -pan)
    if "lead" in fl:
        for (bo, du, m) in LEAD[chn]:
            if bo < nb:
                add(M, t0 + bo * BEAT, bell(m, du * BEAT), 0.6, 0.1)
                add(M, t0 + bo * BEAT + 0.375, bell(m, du * BEAT), 0.18, -0.3)

# final chord at 62
fc = CH["C"]
add(M, 62.0, pad(fc["pad"] + [67, 72], 3.6), 1.6)
add(M, 62.0, kick(), 1.0)
add(M, 62.0, crash(), 0.9)
for i, m in enumerate([72, 76, 79, 84, 88]):
    add(M, 62.0 + i * 0.06, bell(m, 2.5), 0.5, (-1) ** i * 0.3)
add(M, 62.0, bass(36, 1.6), 0.9)

# light bus processing
mx = max(np.abs(L).max(), np.abs(R).max())
L /= mx
R /= mx
L[:] = np.tanh(L * 1.6) / np.tanh(1.6)
R[:] = np.tanh(R * 1.6) / np.tanh(1.6)

# ---------- ducking ----------
T = np.arange(N) / SR
duck = np.full(N, 0.80)
speech = [  # (start, end, level)
    (0.55, 1.65, 0.24), (1.65, 2.5, 0.42), (2.5, 7.2, 0.24),
    (7.75, 14.65, 0.24),
    (15.5, 23.5, 0.30),
    (24.05, 31.8, 0.24),
    (31.95, 39.75, 0.30),
    (44.15, 50.95, 0.24),
    (51.25, 57.0, 0.24),
    (57.0, 62.0, 0.62),
]
for (a, b, lv) in speech:
    duck[(T >= a) & (T < b)] = lv
k = int(0.22 * SR)
duck = np.convolve(np.pad(duck, k, mode="edge"), np.ones(k) / k, mode="same")[k:-k]
# intro fade-in, outro fade-out
duck *= np.clip(T / 0.25, 0, 1)
duck *= np.clip((DUR - 0.15 - T) / 2.6, 0, 1) ** 1.5
L *= duck
R *= duck

# ---------- SFX placement ----------
X = (SFX_L, SFX_R)
add(X, 0.18, sfx_ding(), 0.9)                      # S1 notification
add(X, 5.85, sfx_pop(), 0.6)                       # MORE SCREEN TIME?
add(X, 7.22, sfx_whoosh(0.5, 500, 6000), 0.8)      # zoom S1->S2
add(X, 9.3, sfx_pop(440), 0.35)                    # WHAT IF...
add(X, 12.75, riser(0.8, 500, 6000), 0.55)         # rising whoosh into CREATE
add(X, 13.52, sfx_pop(660), 0.8)                   # CREATE pop
add(X, 15.0, sfx_impact(), 0.45)                   # drop into S3
add(X, 15.35, sfx_pop(), 0.5)                      # CREATE WITH AI
for tt, pn in ((17.0, -0.3), (19.55, 0.0), (20.3, 0.3)):
    add(X, tt, sfx_click(), 0.9, pn)
    add(X, tt + 0.03, sfx_pop(700), 0.4, pn)
add(X, 21.2, sfx_whoosh(0.4), 0.5)                 # BUILD WITH TECHNOLOGY
add(X, 21.4, sfx_pop(), 0.5)
for tt, pn in ((21.9, -0.3), (22.85, 0.3)):
    add(X, tt, sfx_click(), 0.9, pn)
    add(X, tt + 0.03, sfx_pop(700), 0.4, pn)
add(X, 23.7, sfx_whoosh(0.55, 300, 5000), 0.8)     # S3->S4
add(X, 26.35, sfx_pop(480), 0.4)                   # FUTURE BUILDERS CLUB PRESENTS
add(X, 28.25, sfx_chime(), 1.0)                    # logo reveal chime
add(X, 31.72, sfx_whoosh(0.5, 500, 6000), 0.8)     # zoom S4->S5
add(X, 32.25, sfx_typing(1.2), 0.55)               # typing
add(X, 32.3, sfx_pop(), 0.35)
for tt in (33.8, 34.45, 35.5, 36.3):
    add(X, tt, sfx_click(), 0.9)
    add(X, tt + 0.03, sfx_pop(620), 0.45)
add(X, 37.6, sfx_typing(0.9), 0.4)
add(X, 39.6, sfx_whoosh(0.55, 600, 7000), 0.8)     # upward move
add(X, 40.0, sfx_impact(), 0.7)                    # DEMO DAY
add(X, 40.05, sfx_pop(400), 0.5)
add(X, 42.0, sfx_impact(), 0.9)                    # I MADE THIS!
add(X, 42.0, sfx_sparkle(1.6), 1.0)
add(X, 42.0, sfx_chime((76, 79, 84, 88)), 0.8)
add(X, 43.8, sfx_whoosh(0.35), 0.5)
add(X, 48.2, sfx_pop(560), 0.6)                    # REGISTRATION IS OPEN!
add(X, 48.25, sfx_sparkle(0.6), 0.45)
add(X, 49.9, sfx_pop(480), 0.4)                    # JOIN THE HOLIDAY LAB
add(X, 50.75, sfx_whoosh(0.6, 300, 4000), 0.5)     # soft transition
add(X, 56.75, sfx_whoosh(0.6, 300, 6000), 0.8)     # wipe to end card
add(X, 57.2, sfx_impact(), 0.6)
add(X, 57.55, sfx_chime(), 0.7)
for i, tt in enumerate((58.0, 58.5, 58.9, 59.3, 59.8, 60.3)):
    add(X, tt, sfx_pop(480 + 40 * i), 0.4)
add(X, 60.35, sfx_sparkle(1.0), 0.5)

SFX_GAIN = 0.42
outL = L * 0.9 + SFX_L * SFX_GAIN
outR = R * 0.9 + SFX_R * SFX_GAIN
pk = max(np.abs(outL).max(), np.abs(outR).max())
if pk > 0.97:
    outL, outR = outL / pk * 0.97, outR / pk * 0.97
st = np.stack([outL, outR], axis=1)
w = wave.open(sys.argv[1], "wb")
w.setnchannels(2)
w.setsampwidth(2)
w.setframerate(SR)
w.writeframes((st * 32767).astype(np.int16).tobytes())
w.close()
print("ok peak", pk)
