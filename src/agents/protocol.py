"""ReAct action protocol: parsing the structured action out of LLM output.

The agent reasons in prose, then emits one JSON action (ideally fenced in a
```json block). We extract it robustly: fenced block first, else the first
balanced top-level JSON object that parses.
"""

from __future__ import annotations

import json
import re
from typing import Optional

# action verbs
FINISH = "finish"
CALL_SKILL = "call_skill"
CALL_AGENT = "call_agent"
CALL_MCP = "call_mcp"

_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _first_balanced_object(text: str) -> Optional[dict]:
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        start = None
    return None


def extract_json(text: str) -> Optional[dict]:
    """Return the first JSON object in ``text`` (fenced block preferred, else the
    first balanced top-level object), or None. No schema requirement."""
    m = _FENCED.search(text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return _first_balanced_object(text)


def parse_action(text: str) -> Optional[dict]:
    """Return the embedded action dict (must have an ``action`` key), or None."""
    obj = extract_json(text)
    if isinstance(obj, dict) and "action" in obj:
        return obj
    return None
