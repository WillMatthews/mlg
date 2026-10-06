"""MLG-ify a video: quickscope -> hitmarkers + airhorn -> deep-fried dubstep drop -> deal with it."""

import argparse
import io
import json
import math
import random
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

from . import sfx, sprites

SCOPE_IN = 0.35    # seconds scoped in before the shot (it's a QUICKscope)
QS_FPS = 25        # the green-screen quickscope animation's frame rate
GUN_LEAD = 0.4     # gun slides into view this long before the raise
SLOWMO = 0.3       # source playback speed after the shot
FIRST = 0.9        # slow-mo aftermath of the shot before the replays
REPLAYS = 2        # instant replays of the kill, each harder than the last
REPLAY_LEN = 1.0
REPLAY_SHOT = 0.55 # where in each replay the shot lands
DROP_GAP = 0.25    # last replay -> drop
ILLUM_LEN = 2.6    # "illuminati confirmed" interlude after the drop
WEED_LEN = 1.6     # smoke weed everyday
DEAL_LEN = 1.8     # deal with it


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         check=True, capture_output=True, text=True).stdout
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        raise ValueError("input has no video stream")
    num, den = map(int, v["r_frame_rate"].split("/"))
    return {
        "w": int(v["width"]), "h": int(v["height"]), "fps": num / den,
        "duration": float(info["format"]["duration"]),
        "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
    }


def load_audio(path, has_audio):
    if not has_audio:
        return np.zeros(0, np.float32)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sfx.SR),
                          "-f", "f32le", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def loudest_moment(audio, duration):
    """Time of the loudest 50ms window, kept late enough to fit the scope-in."""
    lo = SCOPE_IN + 0.6  # room for the gun raise
    if len(audio) < sfx.SR or duration <= lo:
        return max(lo, duration * 0.6)
    win = int(0.05 * sfx.SR)
    rms = np.sqrt(np.convolve(audio ** 2, np.ones(win) / win, mode="same"))
    rms[: int(lo * sfx.SR)] = 0
    return float(np.argmax(rms) / sfx.SR)


class FrameReader:
    """Sequential decoder that serves frames for a monotonically non-decreasing source time."""

    def __init__(self, path, w, h, fps):
        self.w, self.h, self.fps = w, h, fps
        self.errors = tempfile.TemporaryFile(mode="w+b")
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h},fps={fps}",
                                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=self.errors)
        self.idx, self.frame = -1, None
        self.size = w * h * 3
        self.keep = range(0)  # frame indices cached so replays can rewind
        self.cache = {}

    def cache_window(self, t0, t1):
        self.keep = range(max(0, int(t0 * self.fps)), int(t1 * self.fps) + 1)

    def get(self, t):
        want = max(0, int(t * self.fps))
        if want < self.idx and want in self.cache:  # rewound into the replay window
            return Image.frombytes("RGB", (self.w, self.h), self.cache[want])
        while self.idx < want:
            buf = self.proc.stdout.read(self.size)
            if len(buf) < self.size:
                code = self.proc.wait()
                if code:
                    self.errors.seek(0)
                    raise RuntimeError("video decoding failed: " + self.errors.read().decode(errors="replace").strip())
                if self.frame is None:
                    raise RuntimeError("input video contains no decodable frames")
                break  # EOF: hold the last frame
            self.frame, self.idx = buf, self.idx + 1
            if self.idx in self.keep:
                self.cache[self.idx] = buf
        return Image.frombytes("RGB", (self.w, self.h), self.frame)

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()  # slow-mo / freeze may stop reading before EOF
        self.proc.stdout.close()
        self.proc.wait()
        self.errors.close()


@dataclass
class Particle:
    sprite: Image.Image
    t0: float
    x: float
    vy: float
    vx: float
    spin: float


def smoothstep(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class MLG:
    def __init__(self, w, h, fps, moment, target, seed, drop=None, drop_start=0.0, drop_len=6.0, bpm=140.0,
                 *, weed=True, deal_with_it=True, illuminati=True, replays=True):
        self.w, self.h, self.fps = w, h, fps
        self.M = moment
        self.weed = weed
        self.deal_with_it = deal_with_it
        self.illuminati = illuminati
        self.replays = REPLAYS if replays else 0
        self.R0 = moment + FIRST                                   # instant replays start
        self.D = self.R0 + self.replays * REPLAY_LEN + DROP_GAP         # the drop
        self.shots = [moment] + [self.R0 + k * REPLAY_LEN + REPLAY_SHOT for k in range(self.replays)]
        if drop:
            self.drop_audio = sfx.decode(drop, drop_start, drop_len, trim_silence=False)
            if not len(self.drop_audio):
                raise ValueError("drop contains no audio at --drop-start")
            fade = min(len(self.drop_audio), int(0.3 * sfx.SR))
            self.drop_audio[-fade:] *= np.linspace(1, 0, fade)
            self.beat = 60.0 / bpm
        else:
            self.drop_audio, self.beat = sfx.dubstep_drop(bars=4)
        self.E = self.D + len(self.drop_audio) / sfx.SR
        self.W = self.E + (ILLUM_LEN if illuminati else 0)      # smoke weed everyday
        self.DW = self.W + (WEED_LEN if weed else 0)      # deal with it
        self.clips = {
            "airhorn": sfx.load("airhorn", sfx.airhorn),
            "hitmarker": sfx.load("hitmarker", sfx.hitmarker),
            "sniper": sfx.load("sniper", sfx.sniper),
            "mom": sfx.load("mom_get_the_camera", lambda: sfx.voice("mom get the camera", pitch=70, speed=170)),
            "triple": sfx.load("oh_baby_a_triple", lambda: sfx.voice("oh baby a triple", pitch=35, speed=140)),
            "wow": sfx.load("wow", lambda: sfx.voice("wow", pitch=99, speed=120)),
            "weed": sfx.load("smoke_weed_everyday", lambda: sfx.voice("smoke weed every day", pitch=10, speed=120)),
            "deal": sfx.load("deal_with_it", lambda: sfx.voice("deal with it", pitch=20, speed=130)),
            "rekt": sfx.load("get_rekt", lambda: sfx.voice("get rekt", pitch=30, speed=150)),
            "damn": sfx.load("damn_son", lambda: sfx.voice("damn son where'd you find this", pitch=40, speed=160)),
            "xfiles": sfx.load("illuminati", lambda: sfx.voice("illuminati confirmed", pitch=0, speed=110)),
            "omg": sfx.load("oh_my_god", lambda: sfx.voice("oh my god", pitch=90, speed=150)),
            "wombo": sfx.load("wombo_combo", lambda: sfx.voice("wombo combo", pitch=80, speed=170)),
            "smash_ohh": sfx.load("smash_ohh", lambda: sfx.voice("oh! oh! ohhhh!", pitch=90, speed=170)),
            "crowd_ohh": sfx.load("crowd_ohh", lambda: np.zeros(1, np.float32)),
        }
        # Voice lines back to back during the drop.
        dur = lambda k: len(self.clips[k]) / sfx.SR
        self.mom_at = self.D + 0.05
        self.triple_at = min(self.mom_at + dur("mom") + 0.05, self.E - 1.0)
        self.damn_at = min(self.triple_at + dur("triple") + 0.05, self.E - 1.0)
        self.total = self.DW + (DEAL_LEN if deal_with_it else 0)
        self.tx, self.ty = target[0] * w, target[1] * h
        self.rnd = random.Random(seed)
        s = h / 720
        self.s = s
        self.scope = sprites.scope_overlay(w, h, sprites.load("scope", lambda: None))
        qs = sprites.load_quickscope(h)
        self.qs_raise, self.qs_fire, qs_off = qs if qs else ([], [], (0, 0))
        self.qs_x = qs_off[0] + (w - h * 16 / 9) / 2  # the green screen is 16:9; centre it
        self.qs_y = qs_off[1]
        self.raise_at = self.M - SCOPE_IN - len(self.qs_raise) / QS_FPS
        # Real meme images from assets/ (./fetch_assets.sh), procedural fallbacks otherwise.
        fit = sprites.fit
        self.hit = fit(sprites.load("hitmarker", sprites.hitmarker), width=int(110 * s))
        self.eye = fit(sprites.load("illuminati", sprites.illuminati), width=int(400 * s))
        self.shades = fit(sprites.load("shades", sprites.deal_with_it), width=int(300 * s), nearest=True)
        bag = sprites.load("doritos", sprites.dorito)
        can = sprites.load("mtn_dew", sprites.mtn_dew)
        weed = sprites.load("weed", lambda: None)
        doge = sprites.load("doge", lambda: None)
        thug = sprites.load("thug_life", lambda: None)
        rifle = sprites.load("intervention", lambda: None)
        logo = sprites.load("mlg_logo", lambda: None)
        obey = sprites.load("obey", lambda: None)
        self.rifle = rifle and fit(rifle, width=int(w * 0.55))
        self.logo = logo and fit(logo, width=int(170 * s))
        self.obey = obey and fit(obey, width=int(250 * s))
        joint = sprites.load("joint", lambda: None)
        self.joint = self.weed and joint and fit(joint, width=int(300 * s))
        flare = sprites.load("lens_flare", lambda: None)
        sanic = sprites.load("sanic", lambda: None)
        self.flare = flare and fit(flare, width=int(w * 0.7))
        self.sanic = sanic and fit(sanic, height=int(h * 0.55))
        self.frog = [fit(f, height=int(h * 0.38)) for f in sprites.load_frames("frog")]
        self.doge = doge and fit(doge, height=int(260 * s))
        self.thug = thug and fit(thug, height=int(200 * s))
        self.snoop = [fit(f, height=int(h * 0.7)) for f in sprites.load_frames("snoop")]
        snacks = ([fit(bag, height=int(self.rnd.uniform(160, 240) * s)) for _ in range(3)]
                  + [fit(can, height=int(self.rnd.uniform(160, 230) * s)) for _ in range(3)])
        leaves = [fit(weed, height=int(self.rnd.uniform(90, 170) * s)) for _ in range(3)] if weed else []

        def rain(pool, t0, t1, count):
            return [Particle(self.rnd.choice(pool), self.rnd.uniform(t0, t1), self.rnd.uniform(0, w),
                             self.rnd.uniform(300, 700) * s, self.rnd.uniform(-80, 80) * s,
                             self.rnd.uniform(-540, 540)) for _ in range(count)]

        self.particles = rain(snacks, self.D, self.E - 0.6, 24)
        if leaves and self.weed:
            self.particles += rain(leaves, self.W, self.DW, 14)
        b = self.beat
        bars = max(1, round((self.E - self.D) / (4 * b)))
        self.kicks = [self.D + bar * 4 * b + o for bar in range(bars) for o in (0, 2.5 * b)]
        self.snares = [self.D + bar * 4 * b + 2 * b for bar in range(bars)]
        # Hitmarker spam: a burst on the shot (round the target), then every 8th note of the drop
        # plus doubles on the kicks (anywhere on screen).
        shot = [st + 0.1 * i for st in self.shots for i in range(4 if st == self.M else 3)]
        spam = [self.D + k * b / 2 for k in range(int((self.E - self.D) / (b / 2)))]
        spam += [k + 0.05 * (i + 1) for k in self.kicks for i in range(2)]
        self.hits = shot + sorted(spam)
        self.hit_pos = ([(self.tx + self.rnd.uniform(-120, 120) * s, self.ty + self.rnd.uniform(-90, 90) * s)
                         for _ in shot]
                        + [(self.rnd.uniform(0.15, 0.85) * w, self.rnd.uniform(0.2, 0.8) * h) for _ in spam])
        self.wows = [(sn, self.rnd.uniform(0.15, 0.85) * w, self.rnd.uniform(0.2, 0.8) * h) for sn in self.snares[:-1]]
        self.wombo_at = self.snares[-1]  # stacked over whatever voice line is playing
        self.sanic_at = self.D + 0.45 * (self.E - self.D)
        self.flares = self.shots + [self.D]
        self.flyby_at = self.D + 4 * b  # 360 Intervention fly-by on bar 2 of the drop

    # --- timing -----------------------------------------------------------
    def replay(self, t):
        """(index, seconds into it) while an instant replay is playing, else None."""
        if self.R0 <= t < self.R0 + self.replays * REPLAY_LEN:
            k = int((t - self.R0) / REPLAY_LEN)
            return k, t - self.R0 - k * REPLAY_LEN
        return None

    def src_time(self, t):
        M = self.M
        if t < M:
            return t
        if t < self.R0:
            return M + (t - M) * SLOWMO
        r = self.replay(t)
        if r:  # rewind to just before the shot; each replay slower than the last
            speed = 1.0 / (1 + r[0])
            return max(0.0, M + (r[1] - REPLAY_SHOT) * speed)
        rend = self.R0 + self.replays * REPLAY_LEN
        return M + FIRST * SLOWMO + max(0.0, min(t, self.E) - rend) * SLOWMO  # frozen in the tail

    def beat_pulse(self, t):
        """1.0 on each beat, decaying, during the drop."""
        if not (self.D <= t < self.E):
            return 0.0
        ph = ((t - self.D) / self.beat) % 1.0
        return math.exp(-ph * 6)

    # --- compositing helpers ----------------------------------------------
    def paste(self, im, spr, cx, cy, angle=0.0, scale=1.0, alpha=1.0):
        if scale != 1.0:
            spr = spr.resize((max(1, int(spr.width * scale)), max(1, int(spr.height * scale))), Image.BILINEAR)
        if angle:
            spr = spr.rotate(angle, resample=Image.BILINEAR, expand=True)
        if alpha < 1.0:
            spr = spr.copy()
            spr.putalpha(spr.getchannel("A").point(lambda a: int(a * alpha)))
        im.alpha_composite(spr, (int(cx - spr.width / 2), int(cy - spr.height / 2)))

    def text(self, im, t, msg, cx, cy, size, t0, wobble=True, colour=None):
        pop = smoothstep((t - t0) / 0.12)
        scale = pop * (1 + (0.08 * math.sin(t * 25) if wobble else 0))
        if scale <= 0.01:
            return
        spr = sprites.meme_text(msg, max(1, int(size * self.s * scale)), colour or sprites.rainbow(t))
        self.paste(im, spr, cx, cy, angle=(6 * math.sin(t * 9) if wobble else 0))

    # --- the frame --------------------------------------------------------
    def frame(self, src: Image.Image, t):
        w, h, s = self.w, self.h, self.s
        M, D, E = self.M, self.D, self.E

        # Camera: scope zoom, drop pulses, shake.
        zoom, shake = 1.0, 0.0
        if M - SCOPE_IN <= t < M:
            zoom = 2.3 + 0.3 * smoothstep((t - (M - SCOPE_IN)) / SCOPE_IN)
        elif self.replay(t):
            k, rel = self.replay(t)
            if rel < REPLAY_SHOT - 0.25:
                zoom = 1.2 + 0.3 * k
            elif rel < REPLAY_SHOT:  # scoped in again
                zoom = 2.6 + 0.6 * k
            else:  # harder punch every time
                zoom = 1.3 + 0.4 * k + (0.8 + 0.4 * k) * math.exp(-(rel - REPLAY_SHOT) * 5)
                shake = (30 + 15 * k) * math.exp(-(rel - REPLAY_SHOT) * 3)
        elif M <= t < D:
            zoom = 1 + 0.6 * math.exp(-(t - M) * 4)
            shake = 25 * math.exp(-(t - M) * 3)
        elif D <= t < E:
            zoom = 1.08 + 0.3 * self.beat_pulse(t)
            shake = 6 + 18 * self.beat_pulse(t)
        elif t < self.W:  # illuminati: slow ominous push-in
            zoom = 1 + 0.3 * smoothstep((t - E) / ILLUM_LEN)
        elif self.W <= t < self.total:
            zoom = 1 + 0.15 * smoothstep((t - self.W) / (self.total - self.W))
        if zoom != 1.0 or shake:
            cw, ch = w / zoom, h / zoom
            cx = self.tx + self.rnd.uniform(-shake, shake) * s
            cy = self.ty + self.rnd.uniform(-shake, shake) * s
            cx = min(max(cx, cw / 2), w - cw / 2)
            cy = min(max(cy, ch / 2), h - ch / 2)
            src = src.resize((w, h), Image.BILINEAR, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))

        # Deep fry during the drop.
        if D <= t < E:
            src = ImageEnhance.Color(src).enhance(2.8)
            src = ImageEnhance.Contrast(src).enhance(1.5)
            src = ImageEnhance.Sharpness(src).enhance(6)
            buf = io.BytesIO()
            src.save(buf, "JPEG", quality=7)
            src = Image.open(buf).convert("RGB")
            if any(0 <= t - sn < 0.08 for sn in self.snares):
                r, g, b = src.split()
                src = Image.merge("RGB", (b, r, g))  # hue slap on the snare
        elif E <= t < self.W:
            src = ImageEnhance.Brightness(ImageEnhance.Color(src).enhance(0.2)).enhance(0.4)
        elif self.replay(t):
            k = self.replay(t)[0]
            if k == 0:  # black & white
                src = ImageEnhance.Contrast(src.convert("L").convert("RGB")).enhance(1.6)
            else:  # fried + channel-swapped
                src = ImageEnhance.Contrast(ImageEnhance.Color(src).enhance(3)).enhance(1.6)
                r_, g_, b_ = src.split()
                src = Image.merge("RGB", (g_, b_, r_))

        im = src.convert("RGBA")

        if self.illuminati and D <= t < E:
            spin = (t - D) * 60
            grow = smoothstep((t - D) / 0.4) * (1 + 0.25 * self.beat_pulse(t))
            self.paste(im, self.eye, w / 2, h / 2, angle=spin, scale=grow, alpha=0.9)
        if E <= t < self.W:  # ILLUMINATI CONFIRMED
            k = (t - E) / ILLUM_LEN
            self.paste(im, self.eye, w / 2, h * 0.45, angle=8 * math.sin(t * 3), scale=0.2 + 1.3 * smoothstep(k / 0.8))
            if k > 0.25:
                self.text(im, t, "ILLUMINATI CONFIRMED", w / 2, h * 0.88, 80, E + 0.25 * ILLUM_LEN,
                          wobble=False, colour=(120, 255, 120))
        if self.snoop and (D <= t < E or self.W <= t < self.DW):
            f = self.snoop[int((t - D) * 20) % len(self.snoop)]  # GIF runs at 20fps
            if t < E:
                self.paste(im, f, w * 0.13, h - f.height / 2)
            else:  # smoke weed everyday: Snoop takes centre stage
                self.paste(im, f, w * 0.5, h - f.height * 0.55, scale=1.3)
        for p in self.particles:
            dt = t - p.t0
            if 0 <= dt and t < self.DW:
                y = -150 * s + p.vy * dt + 400 * s * dt * dt
                if y < h + 200 * s:
                    self.paste(im, p.sprite, p.x + p.vx * dt, y, angle=p.spin * dt)

        # First-person Intervention: idle -> raise -> (scoped) -> shot -> bolt cycle.
        gun = None
        lift = 0.0
        if self.qs_raise and self.raise_at - GUN_LEAD <= t < self.raise_at:
            gun = self.qs_raise[0]
            lift = (1 - smoothstep((t - self.raise_at + GUN_LEAD) / (GUN_LEAD * 0.6))) * gun.height
        elif self.qs_raise and self.raise_at <= t < M - SCOPE_IN:
            gun = self.qs_raise[min(len(self.qs_raise) - 1, int((t - self.raise_at) * QS_FPS))]
        elif self.qs_fire and 0 <= t - M - 0.04 < min(len(self.qs_fire) / QS_FPS, FIRST - 0.04):
            gun = self.qs_fire[int((t - M - 0.04) * QS_FPS)]
        if gun is not None:
            im.alpha_composite(gun, (int(self.qs_x), int(self.qs_y + lift)))

        r = self.replay(t)
        if (M - SCOPE_IN <= t < M + 0.04) or (r and REPLAY_SHOT - 0.25 <= r[1] < REPLAY_SHOT + 0.04):
            sway = 4 * s * math.sin(t * 7)
            im.alpha_composite(self.scope, (int(sway), int(sway * 0.6)))

        if self.frog and D <= t < E:  # rainbow frog bobbing at the right edge
            f = self.frog[int((t - D) * 20) % len(self.frog)]
            self.paste(im, f, w - f.width * 0.45, h - f.height * 0.5 + 15 * s * math.sin(t * 16))
        if self.sanic and 0 <= t - self.sanic_at < 0.5:  # gotta go fast
            k = (t - self.sanic_at) / 0.5
            self.paste(im, self.sanic, -0.3 * w + 1.6 * w * k, h * 0.55, angle=-15)
        for ft in self.flares:  # lens flare sweep
            if self.flare and 0 <= t - ft < 0.6:
                k = (t - ft) / 0.6
                self.paste(im, self.flare, w * (0.2 + 0.6 * k), h * 0.4, alpha=math.sin(math.pi * k))
        if t < M - SCOPE_IN:  # the Sony Vegas default nobody deleted
            im.alpha_composite(sprites.sample_text(int(46 * s)), (int(40 * s), int(h * 0.75)))

        if self.joint and D <= t < E:  # spinning blunt
            self.paste(im, self.joint, w * 0.8, h * 0.32, angle=-720 * (t - D))
        if self.joint and self.W <= t < self.DW:  # flanking Snoop
            self.paste(im, self.joint, w * 0.2, h * 0.45, angle=-540 * t, scale=1.3)
            self.paste(im, self.joint, w * 0.8, h * 0.45, angle=540 * t, scale=1.3)
        if self.rifle and 0 <= t - self.flyby_at < 0.9:  # 360 no-scope fly-by
            k = (t - self.flyby_at) / 0.9
            self.paste(im, self.rifle, -0.3 * w + 1.6 * w * k, h * (0.6 - 0.2 * math.sin(math.pi * k)), angle=360 * k)

        for (ht, (hx, hy)) in zip(self.hits, self.hit_pos):
            if 0 <= t - ht < 0.2:
                self.paste(im, self.hit, hx, hy)

        if r and (r[1] * 4) % 1 < 0.6:  # blinking replay bug
            self.text(im, t, "REPLAY" if r[0] == 0 else "REPLAY x2", w * 0.82, h * 0.1, 70,
                      self.R0 + r[0] * REPLAY_LEN, wobble=False, colour=(255, 30, 30))
        if r and r[1] >= REPLAY_SHOT:
            self.text(im, t, ["NO SCOPE?!", "GET REKT M8"][r[0] % 2], w / 2, h * 0.3, 120,
                      self.shots[r[0] + 1])
        if M <= t < self.R0:
            self.text(im, t, "QUICKSCOPED", w / 2, h * 0.25, 110, M)
            if t > M + 0.45:
                self.text(im, t, "GET REKT", w * 0.78, h * 0.8, 70, M + 0.45, colour=(255, 40, 40))
        if D <= t < E:
            if t < self.triple_at + 0.3:
                self.text(im, t, "MOM GET THE CAMERA", w / 2, h * 0.14, 80, self.mom_at)
            if t > self.triple_at:
                self.text(im, t, "OH BABY A TRIPLE", w / 2, h * 0.86, 80, self.triple_at)
            if t > self.damn_at:
                self.text(im, t, "DAMN SON", w * 0.75, h * 0.5, 100, self.damn_at, colour=(255, 60, 60))
            if self.wombo_at <= t < self.wombo_at + 1.2:
                self.text(im, t, "WOMBO COMBO", w / 2, h * 0.5, 130, self.wombo_at)
            for (wt, wx, wy) in self.wows:
                if 0 <= t - wt < 0.6:
                    if self.doge:
                        self.paste(im, self.doge, wx, wy + 60 * s, scale=smoothstep((t - wt) / 0.1))
                    self.text(im, t, "WOW", wx, wy - 90 * s, 120, wt, colour=(255, 255, 0))

        if self.W <= t < self.DW:
            self.text(im, t, "SMOKE WEED EVERYDAY", w / 2, h * 0.15, 80, self.W, colour=(60, 220, 60))
        if self.deal_with_it and t >= self.W:
            fall = smoothstep((t - self.DW + 0.8) / 0.8)
            shades_y = -100 * s + (self.ty - 30 * s + 100 * s) * fall
            if self.obey:
                hat_fall = smoothstep((t - self.DW + 0.5) / 0.8)
                self.paste(im, self.obey, w / 2, -200 * s + (self.ty - 150 * s + 200 * s) * hat_fall, angle=-8)
            self.paste(im, self.shades, w / 2, shades_y)
            if t > self.DW:
                self.text(im, t, "DEAL WITH IT", w / 2, h * 0.85, 100, self.DW, wobble=False,
                          colour=(255, 255, 255))
            if self.thug and t > self.DW + 0.4:  # stamp slam
                slam = 1 + 2 * math.exp(-(t - self.DW - 0.4) * 12)
                self.paste(im, self.thug, w * 0.84, h * 0.22, angle=-12, scale=slam)

        if self.logo:  # broadcast bug
            im.alpha_composite(self.logo, (int(16 * s), int(16 * s)))

        for st in self.shots:  # muzzle flash
            if 0 <= t - st < 0.15:
                a = int(255 * (1 - (t - st) / 0.15))
                im.alpha_composite(Image.new("RGBA", (w, h), (255, 255, 255, a)))

        return im.convert("RGB")

    # --- audio --------------------------------------------------------------
    def audio(self, orig):
        n = int(self.total * sfx.SR) + sfx.SR
        out = np.zeros(n, np.float32)

        def place(sig, at, gain=1.0):
            i = int(at * sfx.SR)
            j = min(n, i + len(sig))
            if i < n:
                out[i:j] += gain * sig[: j - i]

        cut = int(self.M * sfx.SR)
        o = orig[:cut].copy()
        if len(o):
            fade = min(len(o), int(0.05 * sfx.SR))
            o[-fade:] *= np.linspace(1, 0, fade)
            place(o, 0, 0.8)
        place(sfx.whoosh(SCOPE_IN), self.M - SCOPE_IN, 0.7)
        c = self.clips
        place(c["sniper"], self.M)
        place(c["omg"], self.M + 0.05, 0.9)
        place(c["rekt"], self.M + 0.45)
        for ht in self.hits:
            place(c["hitmarker"], ht, 0.8)
        place(c["airhorn"][: int((FIRST - 0.1) * sfx.SR)], self.M + 0.12, 0.9)
        for k, st in enumerate(self.shots[1:]):  # every replay: shot, airhorn, and the crowd on the last
            place(c["sniper"][: int((REPLAY_LEN - REPLAY_SHOT) * sfx.SR)], st)
            place(c["airhorn"][: int(0.4 * sfx.SR)], st + 0.08, 0.8)
            if k == self.replays - 1:
                place(c["crowd_ohh"], st + 0.1, 0.9)
        place(self.drop_audio, self.D, 0.8)
        place(c["mom"], self.mom_at, 1.0)
        place(c["triple"], self.triple_at, 1.0)
        place(c["damn"], self.damn_at, 1.0)
        place(c["smash_ohh"], self.wombo_at - len(c["smash_ohh"]) / sfx.SR + 0.15, 1.0)  # builds into it
        place(c["wombo"], self.wombo_at, 1.0)
        for (wt, _, _) in self.wows:
            place(c["wow"], wt, 0.7)
        if self.illuminati:
            place(c["xfiles"][: int(ILLUM_LEN * sfx.SR)], self.E, 1.0)
        if self.weed:
            place(c["airhorn"], self.W, 0.8)
            place(c["weed"][: int(WEED_LEN * sfx.SR)], self.W, 1.0)
        if self.deal_with_it:
            place(c["deal"], self.DW, 1.0)
        return np.tanh(1.3 * out[: int(self.total * sfx.SR)])  # loud, soft-clipped


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sfx.SR)
        wf.writeframes(pcm.tobytes())


def finite_number(value):
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("must be a finite number")
    return number


def positive_number(value):
    number = finite_number(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def nonnegative_number(value):
    number = finite_number(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def target_point(value):
    try:
        point = tuple(float(part) for part in value.split(","))
        if len(point) != 2 or any(not math.isfinite(n) or not 0 <= n <= 1 for n in point):
            raise ValueError
        return point
    except ValueError:
        raise argparse.ArgumentTypeError("target must be x,y with both coordinates between 0 and 1") from None


def output_width(value):
    width = int(value)
    if width < 2:
        raise argparse.ArgumentTypeError("width must be at least 2 pixels")
    return width


def main(argv=None):
    ap = argparse.ArgumentParser(description="MLG-ify a video clip.")
    ap.add_argument("input")
    ap.add_argument("-o", "--output", help="default: <input>_MLG.mp4")
    ap.add_argument("-m", "--moment", type=nonnegative_number, help="time (s) of the big moment; default: loudest point")
    ap.add_argument("--target", type=target_point, default="0.5,0.5", help="scope aim / shades landing point as x,y fractions")
    ap.add_argument("--width", type=output_width, default=1280)
    ap.add_argument("--seed", type=int, default=420)
    ap.add_argument("--drop", help="drop track (default: sounds/drop.*, else synthesised wobble)")
    ap.add_argument("--drop-start", type=nonnegative_number, default=0.0, help="where the drop starts in the track (s)")
    ap.add_argument("--drop-len", type=positive_number, default=8.0, help="seconds of drop to use")
    ap.add_argument("--bpm", type=positive_number, default=140.0, help="drop tempo, for beat-synced zooms")
    sections = ap.add_argument_group("sections (all enabled by default)")
    sections.add_argument("--weed", action=argparse.BooleanOptionalAction, default=True,
                          help="weed outro and joint/leaf overlays")
    sections.add_argument("--deal-with-it", action=argparse.BooleanOptionalAction, default=True,
                          help="shades, hat, and deal-with-it outro")
    sections.add_argument("--illuminati", action=argparse.BooleanOptionalAction, default=True,
                          help="Illuminati outro and eye overlay during the drop")
    sections.add_argument("--replays", action=argparse.BooleanOptionalAction, default=True,
                          help="two instant replays after the shot")
    a = ap.parse_args(argv)

    try:
        render_video(a, ap)
    except KeyboardInterrupt:
        ap.exit(130, "\nmlg: render cancelled\n")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        if isinstance(detail, bytes):
            detail = detail.decode(errors="replace")
        ap.exit(1, f"mlg: {detail or str(exc)}\n")


def render_video(a, ap):
    inp = Path(a.input)
    out = Path(a.output or inp.with_name(inp.stem + "_MLG.mp4"))
    if not inp.is_file():
        ap.error(f"input file does not exist: {inp}")
    if a.drop and not Path(a.drop).is_file():
        ap.error(f"drop file does not exist: {a.drop}")
    if out.resolve() == inp.resolve() or (a.drop and out.resolve() == Path(a.drop).resolve()):
        ap.error("output must not overwrite the input video or drop track")
    if not out.parent.is_dir():
        ap.error(f"output directory does not exist: {out.parent}")
    if out.exists() and not out.is_file():
        ap.error(f"output is not a regular file: {out}")
    for program in ("ffmpeg", "ffprobe"):
        if shutil.which(program) is None:
            ap.error(f"{program} is required; install FFmpeg and add it to PATH")
    try:
        info = probe(inp)
        if not math.isfinite(info["duration"]) or info["duration"] <= 0:
            raise ValueError("input duration must be positive and finite")
        if not math.isfinite(info["fps"]) or info["fps"] <= 0:
            raise ValueError("input frame rate must be positive and finite")
        if info["w"] < 2 or info["h"] < 2:
            raise ValueError("input dimensions must be at least 2 pixels")
    except (subprocess.CalledProcessError, ValueError, KeyError, ZeroDivisionError) as exc:
        ap.error(f"cannot read input video: {exc}")
    if a.moment is not None and a.moment > info["duration"]:
        ap.error(f"moment must be within the input video ({info['duration']:g} seconds)")
    w = min(a.width, info["w"]) // 2 * 2
    h = int(info["h"] * w / info["w"]) // 2 * 2
    if h < 2:
        ap.error("width is too small for this video aspect ratio")
    fps = min(30.0, info["fps"])
    orig = load_audio(inp, info["has_audio"])
    moment = a.moment if a.moment is not None else loudest_moment(orig, info["duration"])
    moment = min(max(moment, SCOPE_IN + 0.3), info["duration"])
    target = a.target

    drop = a.drop or sfx.find_sound("drop")
    mlg = MLG(w, h, fps, moment, target, a.seed, drop, a.drop_start, a.drop_len, a.bpm,
              weed=a.weed, deal_with_it=a.deal_with_it, illuminati=a.illuminati, replays=a.replays)
    print(f"big moment @ {moment:.2f}s, drop @ {mlg.D:.2f}s, output {mlg.total:.1f}s {w}x{h}@{fps:g}", file=sys.stderr)

    # Encode beside the destination so successful replacement is atomic. A failed
    # render leaves any existing output intact and removes its partial files.
    with tempfile.TemporaryDirectory(prefix=".mlg-", dir=out.parent) as tmp:
        wav = Path(tmp) / "mlg.wav"
        staged = Path(tmp) / ("output" + out.suffix)
        write_wav(wav, mlg.audio(orig))
        with tempfile.TemporaryFile(mode="w+b") as errors:
            enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                    "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-", "-i", str(wav),
                                    "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
                                    "-c:a", "aac", "-b:a", "192k", "-shortest",
                                    "-movflags", "+faststart", str(staged)],
                                   stdin=subprocess.PIPE, stderr=errors)
            reader = None
            try:
                reader = FrameReader(inp, w, h, fps)
                reader.cache_window(moment - REPLAY_SHOT - 0.2, moment + FIRST * SLOWMO + 0.2)
                n = int(mlg.total * fps)
                try:
                    for i in range(n):
                        t = i / fps
                        enc.stdin.write(mlg.frame(reader.get(mlg.src_time(t)), t).tobytes())
                        if i % 30 == 0:
                            print(f"\r  frame {i}/{n}", end="", file=sys.stderr)
                    enc.stdin.close()
                except BrokenPipeError:
                    pass  # report FFmpeg's diagnostic below
                code = enc.wait()
                if code:
                    errors.seek(0)
                    raise RuntimeError("video encoding failed: " + errors.read().decode(errors="replace").strip())
                if not staged.is_file() or not staged.stat().st_size:
                    raise RuntimeError("video encoding produced no output")
            finally:
                if reader is not None:
                    reader.close()
                if enc.poll() is None:
                    enc.kill()
                try:
                    enc.stdin.close()
                except BrokenPipeError:
                    pass
                enc.wait()
        staged.replace(out)
    print(f"\r  done -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
