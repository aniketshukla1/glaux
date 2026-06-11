"""DemoLLM — an offline, no-API-key backend so the UI works out of the box.

It inspects the system prompt to play whichever role is calling: the router
returns a small plan, the reflector accepts, and specialists finish their
subtask. Swap in :class:`AnthropicClient` (set ``ANTHROPIC_API_KEY``) for real
reasoning — same interface.
"""

from __future__ import annotations

from typing import Optional

from .gateway import LLMResponse, Message

_PLAN = (
    "```json\n"
    '{"plan": ['
    '{"id": "s1", "role": "coder", "task": "Implement the requested change", "depends_on": []},'
    '{"id": "s2", "role": "researcher", "task": "Summarize and verify the result", "depends_on": ["s1"]}'
    "]}\n```"
)
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
            text = _PLAN
        elif "you review whether" in sys:
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
