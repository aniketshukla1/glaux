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
    "what is", "what are", "document", "overview", "report", "why", "review",
)
# Scientific / technical mechanism (scientist explains, writer writes it up).
_SCIENCE_KW = (
    "protein", "dna", "rna", "mrna", "cell", "molecule", "molecular", "synthesis",
    "crispr", "gene", "genetic", "enzyme", "photosynthesis", "atom", "atomic",
    "quantum", "physics", "chemistry", "chemical", "biology", "biological",
    "reaction", "neuron", "vaccine", "antibody", "mitochondria", "transcription",
    "translation", "metabolism", "evolution",
)
# Systems / engineering build (engineer designs, coder builds, tester verifies).
_ENGINEERING_KW = (
    "architecture", "architect", "microservice", "scalable", "distributed",
    "rate limiter", "load balanc", "database schema", "design a system",
    "design an", "migration", "deploy", "infrastructure", "pipeline", "system for",
    "high availability", "fault tolerant", "monolith",
)
# Comparison / quantitative analysis (analyst breaks it down, writer writes up).
_ANALYSIS_KW = (
    "compare", "comparison", " vs ", "versus", "trade-off", "tradeoff",
    "pros and cons", "benchmark", "evaluate", "recommend", "analyze", "analyse",
    "which is better", "cost-benefit",
)
# Live / current-information task (web specialist fetches, writer summarizes).
_WEB_KW = (
    "latest", "current", "today", "recent", "news", "search the web", "look up",
    "find online", "real-time", "this year", "right now", "trending",
)
_QUESTION_STARTS = {"what", "why", "how", "who", "when", "which", "explain", "describe", "is", "are"}


def _steps(*roles_tasks) -> list:
    """Build a dependency-chained plan: each step depends on the previous one."""
    steps = []
    for i, (role, task) in enumerate(roles_tasks, start=1):
        steps.append(
            {
                "id": f"s{i}",
                "role": role,
                "task": task,
                "depends_on": [f"s{i - 1}"] if i > 1 else [],
            }
        )
    return steps


def _has(text: str, keywords) -> bool:
    # word-boundary match so e.g. "sum" doesn't fire on "summarize"
    return any(re.search(r"\b" + re.escape(k) + r"\b", text) for k in keywords)


def _extract_directive(content: str) -> str:
    for line in content.splitlines():
        if line.strip().upper().startswith("DIRECTIVE:"):
            return line.split(":", 1)[1].strip()
    return content.strip()


def _router_plan(content: str) -> str:
    """Heuristic planner for the offline demo. It composes a *team* that fits the
    directive — a science lab for a mechanism question, an engineering pod for a
    build, an analysis desk for a comparison — so the demo exercises the full
    specialist roster, not just coder/researcher. A real LLM router does this far
    better; this just makes the offline experience representative."""
    directive = _extract_directive(content)
    low = f" {directive.lower()} "

    if _has(low, _SCIENCE_KW):
        # Science lab: a scientist explains the mechanism, a writer writes it up.
        steps = _steps(
            ("scientist", directive),
            ("writer", "Turn the explanation into a clear, well-structured write-up"),
        )
    elif _has(low, _ENGINEERING_KW):
        # Engineering pod: design → build → verify.
        steps = _steps(
            ("engineer", directive),
            ("coder", "Implement the core of the proposed design"),
            ("tester", "Stress-test the implementation and report edge cases"),
        )
    elif _has(low, _ANALYSIS_KW):
        # Analysis desk: an analyst breaks it down, a writer presents it.
        steps = _steps(
            ("analyst", directive),
            ("writer", "Write up the analysis with a clear recommendation"),
        )
    elif _has(low, _WEB_KW):
        # Web team: fetch live information, then summarize it.
        steps = _steps(
            ("web", directive),
            ("writer", "Summarize the findings and cite the sources"),
        )
    elif _has(low, _CODING_KW):
        # Build + verify.
        steps = _steps(
            ("coder", directive),
            ("tester", "Verify correctness and check edge cases"),
        )
    elif _has(low, _RESEARCH_KW):
        steps = _steps(
            ("researcher", directive),
            ("writer", "Synthesize the findings into a clear answer"),
        )
    else:
        first = low.split()[0] if low.split() else ""
        role = "researcher" if (low.strip().endswith("?") or first in _QUESTION_STARTS) else "coder"
        steps = _steps((role, directive))

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
