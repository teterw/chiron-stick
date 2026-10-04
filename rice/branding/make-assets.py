#!/usr/bin/env python3
"""Draw the Chiron Stick boot branding (our own art, so no image files live in the repo): the
constellation logo, six stars forming a C with Sagittarius' arrow flying out of it (Chiron became
that constellation), on a violet night sky. Usage: make-assets.py <output dir>
Writes logo.png, background.png (GRUB + login screen), select_*.png (GRUB menu highlight),
terminal_box_*.png (GRUB console) and plymouth/ (boot splash frames, watermark, password bullet).
Boot branding is static: it doesn't follow the wallpaper (it runs before anyone logs in)."""
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


def _first(*paths):
    return next((p for p in paths if Path(p).exists()), paths[-1])


FONT = _first("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONT_BOLD = _first("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
SKY_TOP, SKY_BOTTOM = (11, 10, 18), (24, 18, 40)
VIOLET, PINK = (139, 92, 246), (236, 72, 153)  # Chiron violet, and the pink it fades into
FG, MUTED = (236, 234, 244), (139, 133, 163)
CARD = (25, 21, 38)  # GRUB console box
SS = 4  # supersampling for smooth edges

# The constellation in a unit square: (x, y, magnitude 0..1). Six stars make a C that opens to
# the upper right; the arrow's three stars fly out through the opening.
C_STARS = [(0.745, 0.279, 0.9), (0.454, 0.173, 0.45), (0.201, 0.361, 0.6), (0.190, 0.613, 0.4),
           (0.376, 0.806, 0.55), (0.675, 0.780, 0.95)]
ARROW = [(0.38, 0.62, 0.45), (0.56, 0.44, 0.55), (0.84, 0.16, 1.0)]
CHEVRON = [(0.84 - 0.12, 0.16), (0.84, 0.16 + 0.12)]  # arrowhead: lines back from the tip


def lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def tint(x, y):
    """Violet at the lower left, pink at the upper right."""
    return lerp(VIOLET, PINK, min(1.0, max(0.0, (x + (1 - y)) / 2 - 0.1)))


def constellation(size, reveal=1.0, arrow=1.0, flare=0.0, twinkle=None, lines_alpha=120):
    """The logo as RGBA. reveal: how much of the C is drawn (stars appear in order, each line grows
    to the next star); arrow: how far the arrow has flown; flare: the tip star's sparkle;
    twinkle: brightness per star (C stars, then arrow stars)."""
    S = size * SS
    stars = C_STARS + ARROW
    bright = twinkle or [1.0] * len(stars)
    halo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    lines = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    core = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dh, dl, dc = ImageDraw.Draw(halo), ImageDraw.Draw(lines), ImageDraw.Draw(core)
    lw = max(SS, round(S * 0.009))

    def line(a, b, f, alpha):
        if f <= 0:
            return
        end = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        mx, my = (a[0] + end[0]) / 2, (a[1] + end[1]) / 2
        dl.line([(a[0] * S, a[1] * S), (end[0] * S, end[1] * S)], fill=tint(mx, my) + (alpha,), width=lw)

    def star(p, b, extra=1.0):
        x, y, mag = p
        col = tint(x, y)
        rh = S * (0.028 + 0.03 * mag) * extra
        dh.ellipse([x * S - rh, y * S - rh, x * S + rh, y * S + rh], fill=col + (int(min(255, 190 * b)),))
        rc = S * (0.008 + 0.02 * mag) * (0.85 + 0.15 * b)
        dc.ellipse([x * S - rc * 1.7, y * S - rc * 1.7, x * S + rc * 1.7, y * S + rc * 1.7], fill=col + (int(170 * b),))
        dc.ellipse([x * S - rc, y * S - rc, x * S + rc, y * S + rc], fill=lerp(FG, (255, 255, 255), 0.5) + (int(255 * min(1, b)),))

    k = reveal * (len(C_STARS) - 1)
    for i in range(len(C_STARS) - 1):
        line(C_STARS[i], C_STARS[i + 1], min(1.0, max(0.0, k - i)), lines_alpha)
    for i, p in enumerate(C_STARS):
        if reveal > 0 and k >= i - 1e-6:
            star(p, bright[i] * (1.0 if reveal >= 1 or i == 0 else min(1.0, 0.35 + (k - i) * 1.5)))
    if arrow > 0:
        ka = arrow * (len(ARROW) - 1)
        for i in range(len(ARROW) - 1):
            line(ARROW[i], ARROW[i + 1], min(1.0, max(0.0, ka - i)), lines_alpha + 30)
        for i, p in enumerate(ARROW):
            if ka >= i - 1e-6:
                star(p, bright[len(C_STARS) + i], 1.0 + (0.35 * flare if i == 2 else 0))
        if arrow >= 1:  # arrowhead
            tip = ARROW[-1]
            for c in CHEVRON:
                line(tip, c, 1.0, lines_alpha + 60)
            # diffraction spikes on the brightest star
            x, y = tip[0] * S, tip[1] * S
            ln, wd = S * (0.06 + 0.13 * flare), S * 0.007 * (1 + flare)
            for dx, dy in ((1, 0), (0, 1)):
                dc.polygon([(x - dx * ln, y - dy * ln), (x + dy * wd, y + dx * wd),
                            (x + dx * ln, y + dy * ln), (x - dy * wd, y - dx * wd)], fill=(255, 255, 255, int(150 + 100 * flare)))
    halo = halo.filter(ImageFilter.GaussianBlur(S * 0.03))
    out = Image.alpha_composite(halo, lines)
    out = Image.alpha_composite(out, core)
    return out.resize((size, size), Image.LANCZOS)


def sky(w, h, seed=7, clear=None):
    """Violet night sky: gradient, two soft nebula glows and a fixed star field.
    clear: (x0, y0, x1, y1) box kept free of stars (behind the logo and text)."""
    im = Image.new("RGB", (w, h), SKY_TOP)
    d = ImageDraw.Draw(im)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(SKY_TOP, SKY_BOTTOM, y / max(1, h - 1)))
    neb = Image.new("RGBA", (w // 8, h // 8), (0, 0, 0, 0))
    dn = ImageDraw.Draw(neb)
    for (cx, cy, rx, ry, col, a) in ((0.22, 0.85, 0.35, 0.28, VIOLET, 46), (0.82, 0.22, 0.30, 0.22, PINK, 26),
                                     (0.55, 0.55, 0.45, 0.30, VIOLET, 18)):
        dn.ellipse([(cx - rx) * w / 8, (cy - ry) * h / 8, (cx + rx) * w / 8, (cy + ry) * h / 8], fill=col + (a,))
    neb = neb.filter(ImageFilter.GaussianBlur(w / 8 * 0.08)).resize((w, h), Image.BICUBIC)
    im = Image.alpha_composite(im.convert("RGBA"), neb)
    rng = random.Random(seed)
    stars = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ds = ImageDraw.Draw(stars)
    for _ in range(int(w * h / 4200)):
        x, y = rng.random() * w, rng.random() * h
        if clear and clear[0] < x < clear[2] and clear[1] < y < clear[3]:
            continue
        m = rng.random() ** 3
        r = 0.5 + 1.4 * m
        col = lerp((255, 255, 255), tint(x / w, y / h), rng.random() * 0.6)
        ds.ellipse([x - r, y - r, x + r, y + r], fill=col + (int(60 + 170 * m),))
    glow = stars.filter(ImageFilter.GaussianBlur(2))
    im = Image.alpha_composite(Image.alpha_composite(im, glow), stars)
    return im


def wordmark(im, cx, y, size, sub_size):
    d = ImageDraw.Draw(im)
    f, fs = ImageFont.truetype(FONT_BOLD, size), ImageFont.truetype(FONT, sub_size)
    text, gap = "CHIRON", size * 0.32
    widths = [d.textlength(ch, font=f) for ch in text]
    x = cx - (sum(widths) + gap * (len(text) - 1)) / 2
    for ch, wd in zip(text, widths):
        d.text((x, y), ch, font=f, fill=FG)
        x += wd + gap
    sub = "STICK  ·  portable PC doctor"
    d.text((cx - d.textlength(sub, font=fs) / 2, y + size * 1.45), sub, font=fs, fill=lerp(VIOLET, FG, 0.35))


def background(w=1920, h=1080):
    logo_px = int(h * 0.26)
    top = int(h * 0.06)
    im = sky(w, h, clear=(w / 2 - logo_px * 0.6, top, w / 2 + logo_px * 0.6, h * 0.47))
    lg = constellation(logo_px)
    im.alpha_composite(lg, (w // 2 - logo_px // 2, top))
    wordmark(im, w / 2, top + logo_px + h * 0.01, int(h * 0.05), int(h * 0.02))
    return im.convert("RGB")


def main(out):
    out = Path(out)
    (out / "plymouth").mkdir(parents=True, exist_ok=True)
    constellation(256).save(out / "logo.png")
    background().save(out / "background.png")
    # GRUB menu highlight, and the console box (9 slices): a dark card with a thin violet edge
    Image.new("RGBA", (8, 8), VIOLET + (80,)).save(out / "select_c.png")
    Image.new("RGBA", (5, 8), lerp(VIOLET, PINK, 0.3) + (255,)).save(out / "select_w.png")
    for part, size in (("c", (8, 8)), ("n", (8, 1)), ("s", (8, 1)), ("e", (1, 8)), ("w", (1, 8)),
                       ("ne", (1, 1)), ("nw", (1, 1)), ("se", (1, 1)), ("sw", (1, 1))):
        Image.new("RGBA", size, CARD + (255,) if part == "c" else VIOLET + (120,)).save(out / f"terminal_box_{part}.png")
    # Plymouth two-step: the throbber loops while it boots (a wave of light runs through the stars),
    # the animation plays once at the end (the arrow's star flares)
    n_stars = len(C_STARS) + len(ARROW)
    frames = 36
    for f in range(frames):
        ph = f / frames
        tw = [0.72 + 0.28 * (0.5 + 0.5 * math.cos(2 * math.pi * (ph - i / n_stars))) for i in range(n_stars)]
        constellation(200, twinkle=tw, flare=0.15 + 0.15 * math.sin(2 * math.pi * ph)).save(out / "plymouth" / f"throbber-{f + 1:04d}.png")
    frames = 30
    for f in range(frames):
        t = f / (frames - 1)
        fl = math.sin(math.pi * t) * 1.0 + 0.15 * t
        constellation(200, flare=fl, twinkle=[1.0 + 0.25 * math.sin(math.pi * t)] * n_stars).save(out / "plymouth" / f"animation-{f + 1:04d}.png")
    constellation(200).save(out / "plymouth" / "bgrt-fallback.png")
    wm = Image.new("RGBA", (300, 87), (0, 0, 0, 0))
    d = ImageDraw.Draw(wm)
    f = ImageFont.truetype(FONT_BOLD, 24)
    text, gap = "CHIRON  STICK", 6
    widths = [d.textlength(ch, font=f) for ch in text]
    x = (300 - sum(widths) - gap * (len(text) - 1)) / 2
    for ch, wd in zip(text, widths):
        d.text((x, 30), ch, font=f, fill=MUTED + (255,))
        x += wd + gap
    wm.save(out / "plymouth" / "watermark.png")
    b = Image.new("RGBA", (10 * SS, 10 * SS), (0, 0, 0, 0))  # password dots: small violet stars
    db = ImageDraw.Draw(b)
    db.ellipse([SS, SS, 9 * SS, 9 * SS], fill=VIOLET + (255,))
    db.ellipse([3.2 * SS, 3.2 * SS, 6.8 * SS, 6.8 * SS], fill=(240, 232, 255, 255))
    b.resize((10, 10), Image.LANCZOS).save(out / "plymouth" / "bullet.png")
    print(f"assets written to {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
