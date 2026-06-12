"""DemoLLM — an offline, no-API-key backend so the UI works out of the box.

It inspects the system prompt to play whichever role is calling: the router
returns a small plan, the reflector accepts, and specialists finish their
subtask. Swap in :class:`AnthropicClient` (set ``ANTHROPIC_API_KEY``) for real
reasoning — same interface.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .gateway import LLMResponse, Message

# A "doing" task (the coder can call skills / MCP tools to act).
_CODING_KW = (
    "build", "implement", "function", "code", "compute", "calculate", "sum",
    "add", "reverse", "sort", "parse", "write a", "create a", "program",
    "algorithm", "fix", "refactor", "script", "convert", "generate",
)
# An "explaining/finding" task (the researcher gathers + synthesizes).
_RESEARCH_KW = (
    "summarize", "summarise", "explain", "describe", "research", "how it works",
    "what is", "what are", "document", "compare", "analyze", "analyse",
    "overview", "report", "why", "pros and cons", "review",
)
_QUESTION_STARTS = {"what", "why", "how", "who", "when", "which", "explain", "describe", "is", "are"}


def _has(text: str, keywords) -> bool:
    # word-boundary match so e.g. "sum" doesn't fire on "summarize"
    return any(re.search(r"\b" + re.escape(k) + r"\b", text) for k in keywords)


def _extract_directive(content: str) -> str:
    for line in content.splitlines():
        if line.strip().upper().startswith("DIRECTIVE:"):
            return line.split(":", 1)[1].strip()
    return content.strip()


def _router_plan(content: str) -> str:
    """Heuristic planner for the offline demo: emit the FEWEST steps that cover
    the directive — one specialist when one role suffices, and split into two
    only when the task has distinct 'do it' + 'explain it' phases."""
    directive = _extract_directive(content)
    low = directive.lower()
    coding = _has(low, _CODING_KW)
    research = _has(low, _RESEARCH_KW)

    if coding and research:
        steps = [
            {"id": "s1", "role": "coder", "task": directive, "depends_on": []},
            {"id": "s2", "role": "researcher", "task": "Summarize and verify the result",
             "depends_on": ["s1"]},
        ]
    elif research:
        steps = [{"id": "s1", "role": "researcher", "task": directive, "depends_on": []}]
    elif coding:
        steps = [{"id": "s1", "role": "coder", "task": directive, "depends_on": []}]
    else:
        first = low.split()[0] if low.split() else ""
        role = "researcher" if (low.rstrip().endswith("?") or first in _QUESTION_STARTS) else "coder"
        steps = [{"id": "s1", "role": role, "task": directive, "depends_on": []}]

    return "```json\n" + json.dumps({"plan": steps}) + "\n```"


_ACCEPT = '```json\n{"verdict": "accept", "reason": "meets the task (demo mode)"}\n```'
_SKILL = (
    "```json\n"
    "{"
    '"name": "reverse_string", '
    '"description": "Reverse a string", '
    '"entrypoint": "run", '
    '"caps": {"time_limit_s": 5}, '
    '"code": "def run(s):\\n    return s[::-1]\\n", '
    '"tests": ["assert run(\\"abc\\") == \\"cba\\"", "assert run(\\"\\") == \\"\\""]'
    "}\n```"
)


class DemoLLM:
    model_id = "demo-offline"

    def complete(
        self,
        messages: list[Message],
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        seed: Optional[int] = None,
    ) -> LLMResponse:
        sys = (system or "").lower()
        goal = messages[-1].content if messages else ""
        if "router for the athena swarm" in sys:
            text = _router_plan(goal)
        elif "you review whether" in sys:
            low = goal.lower()
            if any(k in low for k in ("implement", "function", "code", "build", "reverse", "compute", "parse")):
                text = (
                    "```json\n"
                    '{"verdict": "accept", "reason": "meets the task (demo mode)", '
                    '"synthesize": "a small reusable utility for this kind of task"}\n```'
                )
            else:
                text = _ACCEPT
        elif "synthesize a reusable python skill" in sys:
            text = _SKILL
        else:
            snippet = goal.splitlines()[0][:80] if goal else "the task"
            text = (
                "```json\n"
                f'{{"action": "finish", "result": "(demo) completed: {snippet}", "success": true}}\n'
                "```"
            )
        return LLMResponse(text=text, model_id=self.model_id, usage={}, raw=None)
