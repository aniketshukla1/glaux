#!/usr/bin/env python3
"""Generate the Next.js docs pages from the canonical markdown in docs/.

The markdown in docs/*.md stays the single source of truth (and stays readable on
GitHub). This renders each one to HTML and emits a React page under
site/app/docs/<slug>/page.tsx, so the site never drifts from the docs.

    python scripts/build_site_docs.py
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import shutil
import sys

try:
    import markdown
except ImportError:
    sys.exit("needs 'markdown':  pip install markdown")

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = ROOT / "site" / "app" / "docs"
IMAGES = ROOT / "docs" / "images"
SITE_IMAGES = ROOT / "site" / "public" / "images"

TITLES = {
    "getting-started": "Getting started",
    "architecture": "Architecture",
    "self-evolution": "Self-evolving harness",
    "cli": "CLI reference",
    "api": "HTTP API",
    "configuration": "Configuration",
    "security": "Security model",
}

PAGE = '''// Generated from docs/{slug}.md by scripts/build_site_docs.py — do not edit by hand.
export const metadata = {{ title: {title} }};

export default function Page() {{
  return <div dangerouslySetInnerHTML={{{{ __html: {body} }}}} />;
}}
'''


def render(slug: str) -> str:
    md = markdown.Markdown(extensions=["extra", "sane_lists", "toc"])
    body = md.convert((DOCS / f"{slug}.md").read_text())
    # rewrite inter-doc links (foo.md / foo.html) to Next routes
    body = re.sub(r'href="([a-z0-9-]+)\.(?:md|html)"', r'href="/docs/\1/"', body)
    # external links open in a new tab
    body = re.sub(r'<a href="(https?:[^"]+)"', r'<a href="\1" target="_blank" rel="noreferrer"', body)
    return body


def sync_images() -> None:
    """Mirror docs/images into the site's public dir.

    The README and the site share these assets; keeping the copy manual meant a
    rebuilt demo.gif landed in the README while the site still served the old one.
    """
    if not IMAGES.is_dir():
        return
    SITE_IMAGES.mkdir(parents=True, exist_ok=True)
    for src in sorted(IMAGES.iterdir()):
        if not src.is_file() or src.name.startswith("."):
            continue
        dst = SITE_IMAGES / src.name
        if dst.exists() and dst.read_bytes() == src.read_bytes():
            continue
        shutil.copy2(src, dst)
        print(f"  synced site/public/images/{src.name}")


def main() -> int:
    sync_images()
    slugs = sorted(p.stem for p in DOCS.glob("*.md"))
    for slug in slugs:
        title = f"{TITLES.get(slug, slug.replace('-', ' ').capitalize())} — Athena docs"
        page = PAGE.format(
            slug=slug,
            title=json.dumps(title),
            body=json.dumps(render(slug)),  # JSON string == JS-safe literal
        )
        d = OUT / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "page.tsx").write_text(page)
        print(f"  built site/app/docs/{slug}/page.tsx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
