"""Generative Canvas (A2UI) — a structured UI the swarm can render alongside prose.

A model (or the offline demo) may emit a ```canvas``` fenced JSON block describing
rich components — metrics, tables, charts, callouts — instead of leaving everything
as plain markdown. We pull that block out of the final answer and validate it down
to a small, safe schema; the frontend renders it. Because the answer is part of the
signed run, the rendered canvas is itself auditable — generative UI you can verify.

Block types: heading, text, metric, table, list, code, callout, chart, divider.
Anything malformed or unknown is dropped, never executed.
"""

from __future__ import annotations

import json
import re
from typing import Optional, Tuple

_CANVAS_RE = re.compile(r"```canvas\s*\n(.*?)```", re.DOTALL)
_ALLOWED = {"heading", "text", "metric", "table", "list", "code", "callout", "chart", "divider"}
_MAX_BLOCKS = 40


def _sanitize(spec) -> Optional[dict]:
    if not isinstance(spec, dict):
        return None
    blocks = spec.get("blocks")
    if not isinstance(blocks, list):
        return None
    clean = [b for b in blocks if isinstance(b, dict) and b.get("type") in _ALLOWED]
    if not clean:
        return None
    return {"title": str(spec.get("title") or ""), "blocks": clean[:_MAX_BLOCKS]}


def extract_canvas(text: Optional[str]) -> Tuple[Optional[str], Optional[dict]]:
    """Pull a ```canvas {json}``` block out of `text`. Returns (clean_text, spec|None);
    a missing or malformed block leaves the text untouched and yields None."""
    if not text or "```canvas" not in text:
        return text, None
    m = _CANVAS_RE.search(text)
    if not m:
        return text, None
    try:
        spec = _sanitize(json.loads(m.group(1)))
    except (json.JSONDecodeError, ValueError):
        return text, None
    if spec is None:
        return text, None
    clean = (text[: m.start()] + text[m.end():]).strip()
    return clean, spec
