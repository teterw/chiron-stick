#!/usr/bin/env python3
"""Draw the Chiron Stick boot branding (our own art, so no image files live in the repo):
a heartbeat line in a ring. Usage: make-assets.py <output dir>
Writes logo.png, background.png (GRUB + login screen), select_*.png (GRUB menu highlight) and
plymouth/ (boot splash and disk-unlock screen frames). Boot branding is static: it doesn't follow
the wallpaper (it runs before anyone logs in)."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG, BG2 = (14, 20, 23), (20, 32, 39)
ACCENT, FG, MUTED = (46, 196, 182), (216, 227, 230), (111, 130, 136)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
# Heartbeat (ECG) path in a unit square: flat, P wave, QRS spike, T wave, flat
ECG = [(0.0, .5), (.28, .5), (.33, .44), (.38, .5), (.42, .5), (.45, .58), (.5, .12), (.55, .82), (.59, .5),
       (.66, .5), (.72, .38), (.78, .5), (1.0, .5)]


def ecg_points(x0, y0, w, h):
    return [(x0 + px * w, y0 + py * h) for px, py in ECG]


def logo(size, upto=1.0, faint=False):
    """Ring with the heartbeat line. upto < 1 draws the line only up to that fraction (animation)."""
    s = 4  # supersample for smooth lines
    im = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad, ring = size * s * 0.06, max(2, size * s // 28)
    d.ellipse([pad, pad, size * s - pad, size * s - pad], outline=ACCENT + (255,), width=ring)
    pts = ecg_points(size * s * 0.16, size * s * 0.2, size * s * 0.68, size * s * 0.6)
    line_w = max(2, size * s // 22)
    d.line(pts, fill=MUTED + (90,), width=line_w, joint="curve")  # faint full trace
    if not faint:
        n = max(2, int(round(upto * (len(pts) - 1))) + 1)
        d.line(pts[:n], fill=ACCENT + (255,), width=line_w, joint="curve")
        x, y = pts[n - 1]
        r = line_w * 1.4
        d.ellipse([x - r, y - r, x + r, y + r], fill=FG + (255,))
    return im.resize((size, size), Image.LANCZOS)


def gradient(w, h):
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG, BG2)))
    return im


def background(w=1920, h=1080):
    im = gradient(w, h)
    lg = logo(220)
    im.paste(lg, (w // 2 - 110, int(h * 0.13)), lg)
    d = ImageDraw.Draw(im)
    title = ImageFont.truetype(FONT_BOLD, 54)
    sub = ImageFont.truetype(FONT, 24)
    for text, font, y, col in (("CHIRON STICK", title, int(h * 0.36), FG), ("portable PC doctor", sub, int(h * 0.36) + 74, MUTED)):
        tw = d.textlength(text, font=font)
        d.text(((w - tw) / 2, y), text, font=font, fill=col)
    return im


def main(out):
    out = Path(out)
    (out / "plymouth").mkdir(parents=True, exist_ok=True)
    logo(256).save(out / "logo.png")
    background().save(out / "background.png")
    Image.new("RGBA", (8, 8), ACCENT + (70,)).save(out / "select_c.png")
    Image.new("RGBA", (5, 8), ACCENT + (255,)).save(out / "select_w.png")
    # Plymouth two-step: animation-NNNN (36) and throbber-NNNN (30) frames, 100x100
    for prefix, frames in (("animation", 36), ("throbber", 30)):
        for i in range(frames):
            logo(100, upto=(i + 1) / frames).save(out / "plymouth" / f"{prefix}-{i + 1:04d}.png")
    wm = Image.new("RGBA", (248, 87), (0, 0, 0, 0))
    d = ImageDraw.Draw(wm)
    f = ImageFont.truetype(FONT_BOLD, 26)
    d.text(((248 - d.textlength("CHIRON STICK", font=f)) / 2, 28), "CHIRON STICK", font=f, fill=MUTED + (255,))
    wm.save(out / "plymouth" / "watermark.png")
    logo(200).save(out / "plymouth" / "bgrt-fallback.png")
    print(f"assets written to {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
