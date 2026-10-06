"""Create an original arcade clip for the mlg demo (Pillow + FFmpeg)."""

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 30
MOMENT = 3.2
OUT = Path(__file__).with_name("target_practice.mp4")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
fonts = {s: ImageFont.truetype(FONT, s) for s in (18, 22, 28, 48)}


def frame(t):
    im = Image.new("RGB", (W, H), (9, 15, 28))
    d = ImageDraw.Draw(im)
    for y in range(H):
        v = y / H
        d.line((0, y, W, y), fill=(int(9 + 7 * v), int(15 + 13 * v), int(28 + 20 * v)))
    # Neon perspective grid and a quiet HUD frame the moving target.
    horizon = 430
    for x in range(-1280, 2561, 160):
        d.line((640 + (x - 640) * 0.08, horizon, x, H), fill=(24, 71, 82), width=2)
    for y in (445, 465, 495, 540, 605, 695):
        d.line((0, y, W, y), fill=(24, 71, 82), width=2)
    d.rounded_rectangle((42, 38, 1238, 115), 14, fill=(13, 23, 39), outline=(40, 68, 89), width=2)
    d.text((65, 59), "MLG / TARGET PRACTICE", font=fonts[28], fill=(232, 245, 255))
    d.text((1210, 65), "DEMO 01", anchor="ra", font=fonts[22], fill=(85, 235, 210))
    d.text((65, 145), "ONE SHOT. MAKE IT COUNT.", font=fonts[18], fill=(147, 175, 193))
    d.text((65, 645), "ARCADE RANGE", font=fonts[18], fill=(85, 235, 210))
    d.text((1210, 645), "SCORE  " + ("0000" if t < MOMENT else "1337"), anchor="ra", font=fonts[22], fill=(232, 245, 255))
    if t < MOMENT:
        x = 640 + 245 * math.sin((t - MOMENT) * 1.6)
        y = 360 + 68 * math.sin((t - MOMENT) * 2.4)
        for r, c in ((67, (31, 79, 97)), (51, (72, 226, 207)), (35, (14, 32, 49)), (19, (255, 100, 106))):
            d.ellipse((x-r, y-r, x+r, y+r), fill=c)
        d.line((x-90, y, x-62, y), fill=(85, 235, 210), width=3)
        d.line((x+62, y, x+90, y), fill=(85, 235, 210), width=3)
        d.text((x, y-95), "TARGET", anchor="mm", font=fonts[18], fill=(147, 175, 193))
    else:
        age = t - MOMENT
        for k in range(32):
            a = k * math.tau / 32
            r = 35 + age * (90 + (k % 5) * 34)
            x, y = 640 + math.cos(a) * r, 360 + math.sin(a) * r + age * age * 35
            size = max(2, 10 - age * 3)
            d.rectangle((x-size, y-size, x+size, y+size), fill=(255, 119 + k % 3 * 40, 90))
        d.text((640, 310), "DIRECT HIT", anchor="mm", font=fonts[48], fill=(85, 235, 210))
        d.text((640, 372), "+1337", anchor="mm", font=fonts[28], fill=(232, 245, 255))
    # The aim point is the exact centre at 3.2s.
    for a in range(4):
        dx, dy = math.cos(a * math.pi / 2), math.sin(a * math.pi / 2)
        d.line((640+dx*10, 360+dy*10, 640+dx*23, 360+dy*23), fill=(235, 245, 255), width=2)
    return im


if __name__ == "__main__":
    enc = subprocess.Popen([
        "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264",
        "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT),
    ], stdin=subprocess.PIPE)
    for i in range(8 * FPS):
        enc.stdin.write(frame(i / FPS).tobytes())
    enc.stdin.close()
    if enc.wait():
        raise RuntimeError("FFmpeg failed")
    print(OUT)
