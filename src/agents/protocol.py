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

# greedy capture so nested objects (e.g. a plan with step objects) are kept whole
_FENCED = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)
_EMPTY_PARENS = re.compile(r"\(\)")
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _repair(s: str) -> str:
    """Fix the JSON defects small/instruct models commonly emit: stray empty
    parens and trailing commas. Both are never valid JSON, so this is safe."""
    s = _EMPTY_PARENS.sub("", s)
    s = _TRAILING_COMMA.sub(r"\1", s)
    return s


def _loads_lenient(s: str) -> Optional[dict]:
    for candidate in (s, _repair(s)):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, TypeError):
            continue
    return None


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
                    obj = _loads_lenient(text[start : i + 1])
                    if obj is not None:
                        return obj
                    start = None
    return None


def extract_json(text: str) -> Optional[dict]:
    """Return the first JSON object in ``text`` (fenced block preferred, else the
    first balanced top-level object), tolerating common LLM JSON defects."""
    m = _FENCED.search(text)
    if m:
        obj = _loads_lenient(m.group(1))
        if obj is not None:
            return obj
    return _first_balanced_object(text)


def parse_action(text: str) -> Optional[dict]:
    """Return the embedded action dict (must have an ``action`` key), or None."""
    obj = extract_json(text)
    if isinstance(obj, dict) and "action" in obj:
        return obj
    return None
