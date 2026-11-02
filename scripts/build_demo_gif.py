#!/usr/bin/env python3
"""Render a deterministic terminal-demo GIF (no screen recorder needed).

Types `glaux run "..."`, streams the swarm's signed steps and the answer, verifies
the chain, then *forges one result and verifies again* — because a chain that only
ever prints ✓ proves nothing. The ✗ naming the exact broken block is the demo.

Frame-by-frame with Pillow, so it is reproducible and renders anywhere GitHub does —
the README and the website both use it.

    python scripts/build_demo_gif.py   # -> docs/images/demo.gif
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "demo.gif"

SCALE = 2
W, H = 800, 470
FPS = 14

# palette (rgb)
BG = (12, 15, 22)
BAR = (18, 22, 31)
FG = (226, 232, 240)
MUTED = (148, 163, 184)
DIM = (100, 116, 139)
TEAL = (45, 212, 191)
INDIGO = (129, 140, 248)
GREEN = (52, 211, 153)
RED = (248, 113, 113)
AMBER = (251, 191, 36)

FONT_PATHS = ["/System/Library/Fonts/Menlo.ttc", "/Library/Fonts/DejaVuSansMono.ttf"]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_PATHS:
        if pathlib.Path(p).is_file():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


FONT = _font(15 * SCALE)
FONT_SM = _font(12 * SCALE)

# --- the script: each line is spans of (text, color); `typed` reveals char by char.
Span = tuple[str, tuple]
Line = dict


def line(*spans: Span, typed: bool = False, gap: int = 6) -> Line:
    return {"spans": list(spans), "typed": typed, "gap": gap}


SCRIPT: list[Line] = [
    line(("$ ", DIM), ("glaux run ", FG),
         ('"compare Postgres and MongoDB for a multi-tenant SaaS"', TEAL), typed=True, gap=10),
    line(("  ◆ ", TEAL), ("router      ", TEAL), ("planning the team", DIM)),
    line(("  ◆ ", TEAL), ("analyst     ", INDIGO), ("weighing the trade-offs", DIM)),
    line(("  ◆ ", TEAL), ("researcher  ", INDIGO), ("checking the facts", DIM)),
    line(("  ◆ ", TEAL), ("reflector   ", INDIGO), ("verifying", DIM), gap=10),
    line(("  ● ", GREEN), ("answer", GREEN), gap=4),  # Menlo has no ⬡ — it renders as tofu
    line(("  Postgres is the safer default: row-level security gives", MUTED), typed=True, gap=1),
    line(("  per-tenant isolation in one database, and JSONB covers", MUTED), typed=True, gap=1),
    line(("  the flexible-schema cases Mongo is usually chosen for.", MUTED), typed=True, gap=10),
    line(("$ ", DIM), ("glaux verify --file .glaux/ledger.jsonl", FG), typed=True, gap=6),
    line(("  ✓ chain verified", GREEN), ("   ·   14 signed blocks", DIM), gap=16),
    # the part that makes the ✓ mean something: forge one block, verify again.
    # keep this identical to the README's tamper demo — both must reproduce exactly.
    line(("$ ", DIM), ("sed -i.bak '2s/\"agent_id\":\"[^\"]*\"/\"agent_id\":\"mallory\"/' .glaux/ledger.jsonl", FG),
         typed=True, gap=2),
    line(("  # claim someone else took the second action", AMBER), gap=10),
    line(("$ ", DIM), ("glaux verify --file .glaux/ledger.jsonl", FG), typed=True, gap=6),
    line(("  ✗ CHAIN INVALID", RED), (" at block 1", FG), (" — block hash mismatch", DIM), gap=4),
    line(("  14 blocks read from .glaux/ledger.jsonl", DIM), gap=34),
]


def _spans_text(spans: list[Span]) -> str:
    return "".join(t for t, _ in spans)


def build_frames() -> list[list[list[Span]]]:
    """Produce a list of frames; each frame is a list of visible lines (span lists)."""
    frames: list[list[list[Span]]] = []
    shown: list[list[Span]] = []

    def snapshot():
        frames.append([list(s) for s in shown])

    for ln in SCRIPT:
        spans, typed, gap = ln["spans"], ln["typed"], ln["gap"]
        if typed:
            full = _spans_text(spans)
            shown.append([])
            step = 5  # chars revealed per frame (higher = snappier, smaller GIF)
            for n in range(step, len(full) + step, step):
                shown[-1] = _slice_spans(spans, n)
                snapshot()
            shown[-1] = list(spans)
        else:
            shown.append(list(spans))
            snapshot()
        for _ in range(gap):
            snapshot()
        # keep the window from overflowing — 12 lines is the most that clears the
        # bottom border at H=470 (y starts at 60, line height 30)
        if len(shown) > 12:
            shown = shown[-12:]
    return frames


def _slice_spans(spans: list[Span], n: int) -> list[Span]:
    out: list[Span] = []
    for text, color in spans:
        if n <= 0:
            break
        out.append((text[:n], color))
        n -= len(text)
    return out


def render(visible: list[list[Span]]) -> Image.Image:
    im = Image.new("RGB", (W * SCALE, H * SCALE), BG)
    d = ImageDraw.Draw(im)
    s = SCALE
    # window chrome
    d.rounded_rectangle([6 * s, 6 * s, (W - 6) * s, (H - 6) * s], radius=14 * s, fill=BG, outline=(40, 46, 60), width=s)
    d.rounded_rectangle([6 * s, 6 * s, (W - 6) * s, 42 * s], radius=14 * s, fill=BAR)
    d.rectangle([6 * s, 30 * s, (W - 6) * s, 42 * s], fill=BAR)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([(24 + i * 20) * s, 18 * s, (24 + i * 20 + 11) * s, 29 * s], fill=c)
    d.text(((W / 2 - 42) * s, 15 * s), "glaux — swarm", font=FONT_SM, fill=DIM)

    y = 60 * s
    lh = 30 * s
    for spans in visible:
        x = 22 * s
        for text, color in spans:
            d.text((x, y), text, font=FONT, fill=color)
            x += d.textlength(text, font=FONT)
        y += lh
    return im.resize((W, H), Image.LANCZOS)


def main() -> int:
    states = build_frames()
    frames = [render(v) for v in states]
    # quantize to keep the GIF small; a terminal needs few colors
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pal[0].save(
        OUT, save_all=True, append_images=pal[1:],
        duration=int(1000 / FPS), loop=0, optimize=True, disposal=2,
    )
    kb = OUT.stat().st_size / 1024
    print(f"  wrote {OUT.relative_to(ROOT)}  ({len(frames)} frames, {kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
