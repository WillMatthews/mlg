"""Turn downloaded raw meme images (assets/raw/) into clean transparent sprites (assets/)."""

import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageSequence

ASSETS = Path(__file__).resolve().parent.parent / "assets"
KEY = (255, 0, 255)


def trim(im):
    bbox = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    return im.crop(bbox) if bbox else im


def key_border_white(frame, thresh=60):
    """Make the white background transparent: flood-fill from the border so white
    inside the subject (Snoop's sleeves) survives."""
    rgb = frame.convert("RGB")
    w, h = rgb.size
    seeds = [(x, y) for x in range(0, w, 8) for y in (0, h - 1)] + [(x, y) for y in range(0, h, 8) for x in (0, w - 1)]
    for s in seeds:
        if min(rgb.getpixel(s)) > 200:
            ImageDraw.floodfill(rgb, s, KEY, thresh=thresh)
    a = np.array(rgb)
    alpha = np.where((a == KEY).all(-1), 0, 255).astype(np.uint8)
    out = frame.convert("RGBA")
    out.putalpha(Image.fromarray(alpha))
    return out


def crop_reflection(im):
    """The Dew can PNG has a mirrored reflection under it: cut at the narrowest row in the lower third."""
    a = np.array(im.getchannel("A")) > 8
    widths = a.sum(1)
    lo = int(len(widths) * 0.7)
    cut = lo + int(np.argmin(widths[lo:int(len(widths) * 0.9)]))
    return im.crop((0, 0, im.width, cut))


def mw2_scope(im, lens_r=404.0):
    """IW-engine sniper reticle texture (1024² RGBA, transparent lens, metal tube ring) -> the in-game
    look: keep the genuine reticle + vignette alpha, darken its teal tint, solid black outside the lens."""
    src = np.array(im.convert("RGBA")).astype(np.float32)
    n = src.shape[0]
    c = (n - 1) / 2
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(yy - c, xx - c)
    t = np.clip((r - (lens_r - 6)) / 8, 0, 1)  # hand-off from the vignette to solid black
    out = np.zeros_like(src)
    out[..., :3] = np.where((r < lens_r)[..., None], src[..., :3] * 0.25, 0) * (1 - t[..., None])
    alpha = np.where(r < lens_r, src[..., 3], 255.0) * (1 - t) + 255 * t
    out[..., 3] = np.where(alpha < 4, 0, alpha)
    return Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGBA")


# Frame ranges of one quickscope cycle in the 25fps green screen (youtube xVrayfJ_oI8).
QS_RAISE = range(18, 24)   # hip -> scope
QS_FIRE = range(26, 50)    # unscope + bolt cycle back to idle (24-25 are the scoped view)


def key_green(rgb):
    """Chroma key the pure (0,214,0) screen to alpha, with spill suppression on the edges."""
    a = rgb.astype(np.float32)
    other = np.maximum(a[..., 0], a[..., 2])
    spill = a[..., 1] - other
    # Only bright, strongly green pixels are screen: the gun's dark olive camo must stay opaque.
    key = np.clip((spill - 70) / 60, 0, 1) * np.clip((a[..., 1] - 120) / 50, 0, 1)
    edge = key > 0
    a[..., 1] = np.where(edge, np.minimum(a[..., 1], other + 10), a[..., 1])  # despill the fringe
    return np.dstack([a, 255 * (1 - key)]).clip(0, 255).astype(np.uint8)


def quickscope(video, out):
    """Keyed first-person Intervention frames, cropped to a shared bbox; offsets in 1280x720 coords."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "scale=1280:720", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, 720, 1280, 3)
    keyed = {i: Image.fromarray(key_green(frames[i]), "RGBA") for i in [*QS_RAISE, *QS_FIRE]}
    bbox = None
    for im in keyed.values():
        b = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        bbox = b if bbox is None else (min(bbox[0], b[0]), min(bbox[1], b[1]), max(bbox[2], b[2]), max(bbox[3], b[3]))
    for name, rng in (("raise", QS_RAISE), ("fire", QS_FIRE)):
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        for k, i in enumerate(rng):
            keyed[i].crop(bbox).save(d / f"{k:03d}.png")
    (out / "meta.json").write_text(json.dumps({"bbox": bbox, "frame": [1280, 720], "fps": 25}))
    print(f"quickscope: {len(QS_RAISE)}+{len(QS_FIRE)} frames, bbox {bbox}")


def main():
    raw = ASSETS / "raw"
    for p in sorted(raw.glob("*")):
        slot = p.stem
        if p.suffix == ".mp4" and slot == "quickscope":
            quickscope(p, ASSETS / "quickscope")
            continue
        if p.suffix == ".gif":
            out = ASSETS / slot
            out.mkdir(exist_ok=True)
            frames = [key_border_white(f.copy()) for f in ImageSequence.Iterator(Image.open(p))]
            bbox = None
            for f in frames:  # one shared crop so the dancer doesn't jitter
                b = f.getchannel("A").getbbox()
                bbox = b if bbox is None else (min(bbox[0], b[0]), min(bbox[1], b[1]),
                                               max(bbox[2], b[2]), max(bbox[3], b[3]))
            for i, f in enumerate(frames):
                f.crop(bbox).save(out / f"{i:03d}.png")
            print(f"{slot}: {len(frames)} frames")
            continue
        im = Image.open(p).convert("RGBA")
        if slot == "scope":  # keep the square texture geometry: lens centred, r=404/1024
            mw2_scope(im).save(ASSETS / "scope.png")
            print("scope: MW2 reticle")
            continue
        if slot == "joint":  # blank the little watermark logo in the bottom-left
            a = np.array(im)
            a[int(im.height * 0.34):, : int(im.width * 0.25), 3] = 0
            im = Image.fromarray(a, "RGBA")
        if slot == "mtn_dew":
            im = crop_reflection(trim(im))
        im = trim(im)
        im.save(ASSETS / f"{slot}.png")
        print(f"{slot}: {im.size}")


if __name__ == "__main__":
    main()
