"""Procedurally synthesised MLG sound effects. All mono float32 at SR."""

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .resources import data_directory

SR = 44100
rng = np.random.default_rng(1337)


def _t(dur):
    return np.arange(int(dur * SR)) / SR


def _saw(phase):
    return 2.0 * (phase % 1.0) - 1.0


def _env(n, attack=0.005, release=0.05):
    e = np.ones(n, np.float32)
    a, r = int(attack * SR), int(release * SR)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def _norm(x, peak=0.9):
    m = np.max(np.abs(x)) or 1.0
    return (x / m * peak).astype(np.float32)


def _lowpass(x, cutoff_hz, q=0.0):
    """Chamberlin state-variable lowpass; cutoff may be a per-sample array."""
    cutoff = np.broadcast_to(np.asarray(cutoff_hz, np.float64), x.shape)
    f = 2.0 * np.sin(np.pi * np.clip(cutoff, 20, SR / 6) / SR)
    damp = 2.0 - 2.0 * q
    low = band = 0.0
    out = np.empty_like(x)
    for i in range(len(x)):
        low += f[i] * band
        high = x[i] - low - damp * band
        band += f[i] * high
        out[i] = low
    return out


def airhorn(blasts=(0.12, 0.12, 0.55), gap=0.06):
    """The classic da-da-daaaa air horn: detuned saws, hard clipped."""
    parts = []
    for d in blasts:
        t = _t(d)
        bend = 1.0 + 0.04 * np.exp(-t * 30)  # slight pitch scoop at the start
        x = np.zeros_like(t)
        for f, a in ((466, 1.0), (469, 0.8), (622, 0.6), (932, 0.4), (1244, 0.25)):
            x += a * _saw(np.cumsum(f * bend / SR))
        x = np.tanh(3.0 * x / 2.5)
        parts += [x * _env(len(t), 0.004, 0.02), np.zeros(int(gap * SR))]
    return _norm(np.concatenate(parts), 0.8)


def hitmarker():
    t = _t(0.06)
    click = rng.standard_normal(len(t)) * np.exp(-t * 400)
    ping = np.sin(2 * np.pi * 3200 * t) * np.exp(-t * 90)
    return _norm(click * 0.6 + ping, 0.7)


def sniper():
    t = _t(0.9)
    crack = rng.standard_normal(len(t)) * np.exp(-t * 25)
    boom = np.sin(2 * np.pi * np.cumsum(120 * np.exp(-t * 6) + 35) / SR) * np.exp(-t * 5)
    tail = _lowpass(rng.standard_normal(len(t)), 900) * np.exp(-t * 4) * 3
    return _norm(np.tanh(2 * (crack * 0.7 + boom + tail)), 0.95)


def whoosh(dur=1.0):
    t = _t(dur)
    noise = rng.standard_normal(len(t))
    x = _lowpass(noise, 200 + 5000 * (t / dur) ** 2, q=0.6)
    return _norm(x * (t / dur) ** 1.5, 0.6)


def kick(dur=0.35):
    t = _t(dur)
    f = 40 + 120 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def snare(dur=0.25):
    t = _t(dur)
    n = rng.standard_normal(len(t)) * np.exp(-t * 18)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return 0.6 * n + 0.5 * body


def dubstep_drop(bars=2, bpm=140):
    """Half-time drop: kick on 1, snare on 3, LFO-wobbled saw bass + growls."""
    beat = 60.0 / bpm
    total = bars * 4 * beat
    n = int(total * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)

    def place(sig, at):
        i = int(at * SR)
        j = min(n, i + len(sig))
        out[i:j] += sig[: j - i]

    for b in range(bars):
        s = b * 4 * beat
        place(kick() * 1.2, s)
        place(kick() * 0.9, s + 2.5 * beat)
        place(snare(), s + 2 * beat)
        for k in range(8):  # hats
            place(rng.standard_normal(int(0.03 * SR)) * np.exp(-np.arange(int(0.03 * SR)) / 300) * 0.15,
                  s + k * beat / 2 + beat / 4)

    # Wobble bass: note pattern per beat, LFO rate changes per half-bar.
    notes = [43.65, 43.65, 51.91, 38.89] * bars  # F1, F1, G#1, D#1
    lfo_rates = [2, 4, 3, 8] * bars  # wobbles per beat
    freq = np.repeat(notes, int(beat * SR) + 1)[:n]
    rate = np.repeat(lfo_rates, int(beat * SR) + 1)[:n] / beat
    lfo = 0.5 - 0.5 * np.cos(2 * np.pi * np.cumsum(rate) / SR)
    ph = np.cumsum(freq) / SR
    raw = _saw(ph) + _saw(ph * 1.007) + 0.5 * np.sign(np.sin(2 * np.pi * ph * 0.5))
    bass = _lowpass(raw, 120 + 2600 * lfo ** 2, q=0.85)
    bass = np.tanh(2.5 * bass)
    out += bass * 0.55

    # "BWAAAH" growl stabs on the off-beats of the last bar.
    for k in (1.5, 3.5):
        gt = _t(beat * 0.45)
        g_ph = np.cumsum(87.3 * (1 + 0.5 * np.exp(-gt * 8))) / SR
        g = _lowpass(_saw(g_ph) + _saw(g_ph * 2.01), 300 + 3500 * np.sin(np.pi * gt / gt[-1]), q=0.9)
        place(np.tanh(3 * g) * 0.5, (bars - 1) * 4 * beat + k * beat)

    return _norm(np.tanh(1.4 * out), 0.95), beat


def riser(dur=1.0):
    """Siren pitch-riser into the drop."""
    t = _t(dur)
    f = 300 * 2 ** (3 * t / dur)
    x = _saw(np.cumsum(f) / SR) + 0.5 * rng.standard_normal(len(t)) * (t / dur)
    return _norm(_lowpass(x, 400 + 6000 * t / dur) * (t / dur), 0.5)


SOUNDS_DIR = data_directory("sounds")
AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".opus")


def find_sound(slot, sounds_dir=SOUNDS_DIR):
    for ext in AUDIO_EXTS:
        p = Path(sounds_dir) / f"{slot}{ext}"
        if p.exists():
            return p
    return None


def decode(path, start=0.0, duration=None, trim_silence=True):
    """Decode any audio file to mono float32 at SR, optionally trimming leading silence."""
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start)]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-i", str(path)]
    if trim_silence:
        cmd += ["-af", "silenceremove=start_periods=1:start_threshold=-40dB"]
    cmd += ["-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    x = np.frombuffer(subprocess.run(cmd, check=True, capture_output=True).stdout, np.float32)
    return _norm(x, 0.95) if len(x) else x


def load(slot, fallback, sounds_dir=SOUNDS_DIR):
    """Real clip from sounds/<slot>.* if present, else the procedural fallback()."""
    p = find_sound(slot, sounds_dir)
    if p is not None:
        x = decode(p)
        if len(x):
            return x
    return fallback()


def voice(text, pitch=50, speed=150, voice_name="en-us"):
    """Robot meme voice via espeak-ng. Returns silence if espeak is missing."""
    if not shutil.which("espeak-ng"):
        return np.zeros(int(0.5 * SR), np.float32)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "v.wav"
        subprocess.run(["espeak-ng", "-v", voice_name, "-p", str(pitch), "-s", str(speed),
                        "-a", "200", "-w", str(p), text], check=True, capture_output=True)
        with wave.open(str(p)) as w:
            sr = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    xs = np.interp(np.arange(int(len(x) * SR / sr)) * sr / SR, np.arange(len(x)), x)
    return _norm(np.tanh(2 * xs), 0.9)  # a little saturation = earrape-lite
