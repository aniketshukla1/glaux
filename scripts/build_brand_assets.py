#!/usr/bin/env python3
"""Render the PNG brand assets from the same mark the site uses.

    python scripts/build_brand_assets.py    # -> docs/images/

The owl mark is defined once as SVG (site/public/favicon.svg) and redrawn here on
the same 0..64 grid, so the icon, the README banner and the social cards can never
drift from the favicon. Everything is deterministic — a rebuild is byte-stable.

  icon.png             512x512    avatar / app icon
  banner.png          1280x360    README hero
  social-card.png     1280x640    GitHub social preview + og:image
  linkedin-banner.png 1584x396    LinkedIn page/profile cover
  x-header.png        1500x500    X / Twitter header
"""

from __future__ import annotations

import math
import pathlib
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"

# brand tokens — kept in step with site/app/globals.css
BG = (9, 11, 16)
TEAL = (45, 212, 191)
INDIGO = (129, 140, 248)
FG = (237, 242, 249)
MUTED = (148, 163, 184)

TAGLINE = "A multi-agent swarm that proves its work"

BOLD = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/DejaVuSans-Bold.ttf"]
REG = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/DejaVuSans.ttf"]
MONO = ["/System/Library/Fonts/Menlo.ttc", "/Library/Fonts/DejaVuSansMono.ttf"]


def font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        if pathlib.Path(p).is_file():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def gradient(size: tuple[int, int], c1=TEAL, c2=INDIGO) -> Image.Image:
    """Teal -> indigo along the diagonal, matching the SVG's linearGradient."""
    w, h = size
    g = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(g)
    span = w + h
    for i in range(span):
        t = i / (span - 1)
        d.line([(i, 0), (0, i)], fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    return g


def owl_mark(px: int, stroke: float = 4.0) -> Image.Image:
    """The Athena mark, gradient-filled, on the SVG's 0..64 grid."""
    ss = 4  # supersample, then downsample for clean curves
    n, k = px * ss, px * ss / 64.0
    mask = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(mask)
    w = max(1, round(stroke * k))

    for cx in (23, 41):
        d.ellipse([(cx - 11) * k, 23 * k, (cx + 11) * k, 45 * k], outline=255, width=w)
        r = 3.8 * k
        d.ellipse([cx * k - r, 34 * k - r, cx * k + r, 34 * k + r], fill=255)

    for x1, y1, x2, y2 in ((14, 20, 21, 26), (50, 20, 43, 26)):  # ear tufts
        d.line([x1 * k, y1 * k, x2 * k, y2 * k], fill=255, width=w)
        for x, y in ((x1, y1), (x2, y2)):  # round caps
            r = w / 2
            d.ellipse([x * k - r, y * k - r, x * k + r, y * k + r], fill=255)

    mask = mask.resize((px, px), Image.LANCZOS)
    out = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    out.paste(gradient((px, px)), (0, 0), mask)
    return out


def swarm_field(im: Image.Image, seed: int = 7, density: int = 13000) -> None:
    """The ambient agent field from the dashboard: nodes, and links between near ones."""
    rnd = random.Random(seed)
    w, h = im.size
    pts = [(rnd.uniform(0, w), rnd.uniform(0, h)) for _ in range(max(24, w * h // density))]
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    reach = w * 0.135
    for i, (x1, y1) in enumerate(pts):
        for x2, y2 in pts[i + 1:]:
            dist = math.hypot(x2 - x1, y2 - y1)
            if dist < reach:
                d.line([x1, y1, x2, y2], fill=(*TEAL, int(34 * (1 - dist / reach))), width=1)
    for x, y in pts:
        r = rnd.uniform(1.2, 2.7)
        c = TEAL if rnd.random() < 0.62 else INDIGO
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*c, rnd.randint(55, 150)))
    im.alpha_composite(layer)


def glow(im: Image.Image, cx: int, cy: int, radius: int, color=TEAL, strength: int = 58) -> None:
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius], fill=(*color, strength)
    )
    im.alpha_composite(layer.filter(ImageFilter.GaussianBlur(radius * 0.55)))


def canvas(w: int, h: int, seed: int = 7) -> Image.Image:
    im = Image.new("RGBA", (w, h), (*BG, 255))
    swarm_field(im, seed=seed)
    return im


def centered(d: ImageDraw.ImageDraw, y: int, text: str, f, fill, w: int) -> int:
    tw = d.textbbox((0, 0), text, font=f)[2]
    d.text(((w - tw) / 2, y), text, font=f, fill=fill)
    return d.textbbox((0, 0), text, font=f)[3]


def save(im: Image.Image, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    im.convert("RGB").save(p, optimize=True)
    print(f"  wrote docs/images/{name}  ({im.size[0]}x{im.size[1]}, {p.stat().st_size / 1024:.0f} KB)")


# --- the assets -----------------------------------------------------------


def build_icon(px: int = 512) -> None:
    im = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    r = int(px * 0.22)  # rounded-square, iOS-ish
    plate = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    ImageDraw.Draw(plate).rounded_rectangle([0, 0, px - 1, px - 1], radius=r, fill=(*BG, 255))
    im.alpha_composite(plate)

    field = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    swarm_field(field, seed=3, density=9000)
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, px - 1, px - 1], radius=r, fill=255)
    im.alpha_composite(Image.composite(field, Image.new("RGBA", (px, px), (0, 0, 0, 0)), mask))

    glow(im, px // 2, int(px * 0.53), int(px * 0.30), strength=52)
    m = int(px * 0.62)
    im.alpha_composite(owl_mark(m, stroke=4.4), ((px - m) // 2, (px - m) // 2))
    save(im, "icon.png")


def build_banner(w: int = 1280, h: int = 360) -> None:
    im = canvas(w, h, seed=11)
    glow(im, w // 2, int(h * 0.40), int(h * 0.52), strength=44)

    m = 92
    im.alpha_composite(owl_mark(m, stroke=4.2), ((w - m) // 2, 44))
    d = ImageDraw.Draw(im)
    centered(d, 152, "Athena", font(BOLD, 74), FG, w)
    centered(d, 244, TAGLINE, font(REG, 27), MUTED, w)

    bar = Image.new("RGBA", (w, 3), (0, 0, 0, 0))
    bar.paste(gradient((w, 3)), (0, 0))
    im.alpha_composite(bar, (0, h - 3))
    save(im, "banner.png")


def build_social_card(w: int = 1280, h: int = 640) -> None:
    im = canvas(w, h, seed=5)
    glow(im, w // 2, int(h * 0.34), int(h * 0.40), strength=50)

    m = 118
    im.alpha_composite(owl_mark(m, stroke=4.2), ((w - m) // 2, 96))
    d = ImageDraw.Draw(im)
    centered(d, 238, "Athena", font(BOLD, 92), FG, w)
    centered(d, 350, TAGLINE, font(REG, 32), MUTED, w)

    # the hook: a chain that only ever prints ✓ proves nothing
    mono = font(MONO, 27)
    line = "✗ CHAIN INVALID at block 1 — block hash mismatch"
    tw = d.textbbox((0, 0), line, font=mono)[2]
    x0, y0 = (w - tw) / 2 - 30, 438
    d.rounded_rectangle([x0, y0, x0 + tw + 60, y0 + 66], radius=12,
                        fill=(16, 20, 28, 255), outline=(46, 54, 70, 255), width=1)
    d.text((x0 + 30, y0 + 19), line, font=mono, fill=(248, 113, 113))
    centered(d, 542, "github.com/athena-swarm/athena", font(REG, 25), (110, 125, 148), w)

    bar = Image.new("RGBA", (w, 4), (0, 0, 0, 0))
    bar.paste(gradient((w, 4)), (0, 0))
    im.alpha_composite(bar, (0, h - 4))
    save(im, "social-card.png")


def build_wide(name: str, w: int, h: int, seed: int) -> None:
    """LinkedIn / X covers. Both crop hard on mobile, so everything stays in the
    middle ~60% and nothing important goes near an edge."""
    im = canvas(w, h, seed=seed)
    cx, cy = w // 2, int(h * 0.43)
    glow(im, cx, h // 2, int(h * 0.62), strength=42)

    d = ImageDraw.Draw(im)
    title = font(BOLD, int(h * 0.155))
    tag = font(REG, int(h * 0.070))

    # Align the mark to the wordmark's *optical* centre, not the text box: the
    # ascender box is much taller than the cap height, so anchoring on the box
    # drops the mark well below the letters.
    bx0, by0, bx1, by1 = d.textbbox((0, 0), "Athena", font=title)
    tw, th = bx1 - bx0, by1 - by0
    m = int(h * 0.34)
    gap = int(h * 0.05)

    x = cx - (m + gap + tw) // 2
    im.alpha_composite(owl_mark(m, stroke=4.2), (x, cy - m // 2))
    d.text((x + m + gap - bx0, cy - th // 2 - by0), "Athena", font=title, fill=FG)

    tagw = d.textbbox((0, 0), TAGLINE, font=tag)[2]
    d.text((cx - tagw / 2, cy + m // 2 + gap), TAGLINE, font=tag, fill=MUTED)

    bar = Image.new("RGBA", (w, 4), (0, 0, 0, 0))
    bar.paste(gradient((w, 4)), (0, 0))
    im.alpha_composite(bar, (0, h - 4))
    save(im, name)


def main() -> int:
    build_icon()
    build_banner()
    build_social_card()
    build_wide("linkedin-banner.png", 1584, 396, seed=17)
    build_wide("x-header.png", 1500, 500, seed=23)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
