#!/usr/bin/env bash
# Render a logo's README hero: a seamless 10-second animated WebP.
#   scripts/logo3d/make-hero.sh glaux Glaux "A multi-agent swarm|that proves its work" 98 1.55 docs/images/hero.webp
#   scripts/logo3d/make-hero.sh athenadb AthenaDB "A high-performance|vector database in Rust" 84 1.5 hero.webp
# Needs: npm ci in site/, Google Chrome, img2webp, and a Python with websockets (the project venv has it).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
mark="$1"; name="$2"; tag="$3"; size="$4"; scale="$5"; out="$6"
tmp="$(mktemp -d)"
"${PYTHON:-venv/bin/python}" "$here/render.py" "$tmp" 1040 455 --frames 160 mark="$mark" name="$name" "tag=$tag" \
  nameSize="$size" tagSize=24 textLeft=62 textWidth=440 scale="$scale" offsetX=2.05
img2webp -loop 0 -lossy -q 58 -m 6 -d 62 "$tmp"/f*.png -o "$out" 2>/dev/null
rm -rf "$tmp"
echo "$out: $(($(wc -c < "$out") / 1024)) KB"
