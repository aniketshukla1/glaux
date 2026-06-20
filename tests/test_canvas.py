"""Generative Canvas (A2UI): extraction + sanitization of the ```canvas``` block."""

from __future__ import annotations

import json

from agents.canvas import extract_canvas


def _block(spec):
    return "Here is the answer.\n\n```canvas\n" + json.dumps(spec) + "\n```"


def test_extracts_valid_canvas_and_cleans_text():
    spec = {"title": "Overview", "blocks": [
        {"type": "metric", "items": [{"label": "X", "value": "1"}]},
        {"type": "table", "columns": ["a"], "rows": [["b"]]},
    ]}
    text, canvas = extract_canvas(_block(spec))
    assert text == "Here is the answer."
    assert canvas["title"] == "Overview" and len(canvas["blocks"]) == 2


def test_no_canvas_returns_text_untouched():
    text, canvas = extract_canvas("just a plain answer, no canvas here")
    assert canvas is None and text == "just a plain answer, no canvas here"


def test_malformed_json_is_ignored():
    text = "answer\n\n```canvas\n{not valid json,,}\n```"
    out, canvas = extract_canvas(text)
    assert canvas is None and out == text


def test_unknown_block_types_dropped_and_empty_is_none():
    text, canvas = extract_canvas(_block({"blocks": [{"type": "script", "src": "evil"}, {"type": "text", "text": "ok"}]}))
    assert [b["type"] for b in canvas["blocks"]] == ["text"]  # script dropped
    # a canvas with no valid blocks is treated as absent
    _, none_canvas = extract_canvas(_block({"blocks": [{"type": "iframe"}]}))
    assert none_canvas is None
