"""Procedurally drawn MLG sprites (RGBA PIL images)."""

import math
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .resources import data_directory

FONT_PATHS = [
    "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


@lru_cache(maxsize=None)
def font(size):
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def dorito(size=200):
    im = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(im)
    pad = size * 0.08
    tri = [(size / 2, pad), (size - pad, size - pad), (pad, size - pad)]
    d.polygon(tri, fill=(240, 120, 20, 255), outline=(150, 60, 0, 255), width=max(2, size // 40))
    rnd = random.Random(size)
    for _ in range(size // 3):  # cheese dust
        x, y = rnd.uniform(size * 0.3, size * 0.7), rnd.uniform(size * 0.35, size * 0.85)
        r = rnd.uniform(1, size / 60)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(200, 50, 10, 220))
    return im


def mtn_dew(height=260):
    w = int(height * 0.45)
    im = Image.new("RGBA", (w, height))
    d = ImageDraw.Draw(im)
    top = int(height * 0.08)
    d.rounded_rectangle([0, top, w - 1, height - 1], radius=w // 6, fill=(20, 140, 40, 255))
    for i in range(w // 5):  # cylinder shading
        a = int(90 * (1 - i / (w / 5)))
        d.line([(i, top + 6), (i, height - 6)], fill=(0, 0, 0, a))
        d.line([(w - 1 - i, top + 6), (w - 1 - i, height - 6)], fill=(0, 0, 0, a))
    d.line([(w * 0.62, top + 8), (w * 0.62, height - 8)], fill=(255, 255, 255, 70), width=max(2, w // 12))
    d.rounded_rectangle([w * 0.12, 0, w * 0.88, top + 6], radius=6, fill=(200, 200, 205, 255))
    label = Image.new("RGBA", (height, w))
    ld = ImageDraw.Draw(label)
    f = font(int(w * 0.42))
    ld.text((height * 0.55, w / 2), "MTN DEW", font=f, anchor="mm", fill=(255, 255, 255, 255),
            stroke_width=max(2, w // 25), stroke_fill=(200, 0, 20, 255))
    label = label.rotate(90, expand=True)
    im.alpha_composite(label, (0, 0))
    return im


def illuminati(size=320):
    im = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(im)
    pad = size * 0.05
    h = (size - 2 * pad) * math.sqrt(3) / 2
    y0 = (size - h) / 2
    tri = [(size / 2, y0), (size - pad, y0 + h), (pad, y0 + h)]
    glow = Image.new("RGBA", (size, size))
    ImageDraw.Draw(glow).polygon(tri, fill=(255, 230, 80, 180))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size / 20)))
    d.polygon(tri, fill=(30, 20, 0, 230), outline=(255, 215, 0, 255), width=max(3, size // 30))
    cx, cy, ew, eh = size / 2, y0 + h * 0.62, size * 0.22, size * 0.11
    d.ellipse([cx - ew, cy - eh, cx + ew, cy + eh], fill=(255, 255, 255, 255), outline=(255, 215, 0, 255), width=3)
    r = eh * 0.9
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(40, 120, 200, 255))
    d.ellipse([cx - r / 2, cy - r / 2, cx + r / 2, cy + r / 2], fill=(0, 0, 0, 255))
    for k in range(12):  # rays
        a = -math.pi / 2 + (k - 5.5) * 0.18
        d.line([(cx + math.cos(a) * ew * 1.1, cy + math.sin(a) * eh * 1.6),
                (cx + math.cos(a) * ew * 1.4, cy + math.sin(a) * eh * 2.6)], fill=(255, 215, 0, 255), width=2)
    return im


def hitmarker(size=90):
    im = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(im)
    c, i, o = size / 2, size * 0.14, size * 0.46
    for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        seg = [(c + sx * i, c + sy * i), (c + sx * o, c + sy * o)]
        d.line(seg, fill=(0, 0, 0, 255), width=max(5, size // 9))
        d.line(seg, fill=(255, 255, 255, 255), width=max(3, size // 16))
    return im


def deal_with_it(width=300):
    """Pixel-art 8-bit shades."""
    px = [
        "XXXXXXXXXXXXXXXXXXXXXXXX",
        "XXXXXXXXXXXXXXXXXXXXXXXX",
        "..XWWXXXXXXXXXWWXXXXXXX.",
        "..XWWXXXXXX..XWWXXXXXX..",
        "..XXXXXXXXX..XXXXXXXXX..",
        "...XXXXXXX....XXXXXXX...",
        "....XXXXX......XXXXX....",
    ]
    cell = width // len(px[0])
    im = Image.new("RGBA", (cell * len(px[0]), cell * len(px)))
    d = ImageDraw.Draw(im)
    for y, row in enumerate(px):
        for x, ch in enumerate(row):
            if ch != ".":
                col = (255, 255, 255, 255) if ch == "W" else (0, 0, 0, 255)
                d.rectangle([x * cell, y * cell, (x + 1) * cell - 1, (y + 1) * cell - 1], fill=col)
    return im


def scope(w, h):
    """Full-frame sniper scope overlay: black outside a circle, crosshair, mil-dots."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    r = int(min(w, h) * 0.46)
    cx, cy = w // 2, h // 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 0))
    edge = Image.new("L", (w, h), 0)
    ImageDraw.Draw(edge).ellipse([cx - r, cy - r, cx + r, cy + r], outline=255, width=r // 8)
    vignette = Image.new("RGBA", (w, h), (0, 0, 0, 200))
    im.paste(vignette, (0, 0), edge.filter(ImageFilter.GaussianBlur(r // 12)))
    lw = max(2, w // 500)
    d.line([(cx - r, cy), (cx + r, cy)], fill=(0, 0, 0, 255), width=lw)
    d.line([(cx, cy - r), (cx, cy + r)], fill=(0, 0, 0, 255), width=lw)
    d.line([(cx - r, cy), (cx - r // 3, cy)], fill=(0, 0, 0, 255), width=lw * 4)
    d.line([(cx + r // 3, cy), (cx + r, cy)], fill=(0, 0, 0, 255), width=lw * 4)
    d.line([(cx, cy + r // 3), (cx, cy + r)], fill=(0, 0, 0, 255), width=lw * 4)
    for k in range(-4, 5):
        if k:
            s = r // 10
            d.ellipse([cx + k * s - lw * 2, cy - lw * 2, cx + k * s + lw * 2, cy + lw * 2], fill=(0, 0, 0, 255))
            d.ellipse([cx - lw * 2, cy + k * s - lw * 2, cx + lw * 2, cy + k * s + lw * 2], fill=(0, 0, 0, 255))
    d.ellipse([cx - lw * 2, cy - lw * 2, cx + lw * 2, cy + lw * 2], fill=(255, 0, 0, 255))
    return im


def meme_text(text, size=90, fill=(255, 255, 255), stroke=(0, 0, 0)):
    f = font(size)
    sw = max(3, size // 12)
    l, t, r, b = f.getbbox(text, stroke_width=sw)
    im = Image.new("RGBA", (r - l + 4, b - t + 4))
    ImageDraw.Draw(im).text((2 - l, 2 - t), text, font=f, fill=fill + (255,), stroke_width=sw,
                            stroke_fill=stroke + (255,))
    return im


def rainbow(t):
    """Saturated colour cycling with time t (seconds)."""
    import colorsys
    r, g, b = colorsys.hsv_to_rgb((t * 1.5) % 1.0, 1.0, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


ASSETS_DIR = data_directory("assets")


def fit(im, width=None, height=None, nearest=False):
    """Resize keeping aspect to the given width or height."""
    k = (width / im.width) if width else (height / im.height)
    size = (max(1, round(im.width * k)), max(1, round(im.height * k)))
    return im.resize(size, Image.NEAREST if nearest else Image.LANCZOS)


def load(slot, fallback, assets_dir=ASSETS_DIR):
    """Real meme image assets/<slot>.png if fetched, else the procedural fallback()."""
    p = Path(assets_dir) / f"{slot}.png"
    return Image.open(p).convert("RGBA") if p.exists() else fallback()


def load_frames(slot, assets_dir=ASSETS_DIR):
    """Animated asset as a list of RGBA frames (assets/<slot>/NNN.png), or []."""
    return [Image.open(p).convert("RGBA") for p in sorted((Path(assets_dir) / slot).glob("*.png"))]


def load_quickscope(h, assets_dir=ASSETS_DIR):
    """First-person Intervention quickscope frames scaled to output height h.
    Returns (raise_frames, fire_frames, (x0, y0) paste offset for a 16:9 frame) or None."""
    import json
    d = Path(assets_dir) / "quickscope"
    if not (d / "meta.json").exists():
        return None
    meta = json.loads((d / "meta.json").read_text())
    k = h / meta["frame"][1]
    frames = {n: [fit(Image.open(p).convert("RGBA"), height=round(Image.open(p).height * k))
                  for p in sorted((d / n).glob("*.png"))] for n in ("raise", "fire")}
    x0, y0 = meta["bbox"][:2]
    return frames["raise"], frames["fire"], (x0 * k, y0 * k)


def scope_overlay(w, h, tex=None):
    """Full-frame scope: the MW2 reticle texture (lens r = 404/1024 of the square) centred on black,
    sized so the lens radius is 0.392*h as measured from an MW2 PC screenshot; else the drawn one."""
    if tex is None:
        return scope(w, h)
    size = round(tex.width * (0.392 * h) / (404 / 1024 * tex.width))
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    canvas.paste(tex.resize((size, size), Image.LANCZOS), ((w - size) // 2, (h - size) // 2))
    return canvas


def sample_text(size):
    """Sony Vegas' default title text, left in by accident (on purpose)."""
    f = font_plain(size)
    l, t, r, b = f.getbbox("Sample Text")
    im = Image.new("RGBA", (r - l + 4, b - t + 4))
    ImageDraw.Draw(im).text((2 - l, 2 - t), "Sample Text", font=f, fill=(255, 255, 0, 255))
    return im


@lru_cache(maxsize=None)
def font_plain(size):
    for p in ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default(size)
