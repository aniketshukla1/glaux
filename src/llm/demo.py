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
    # Capture the whole DIRECTIVE block (it may be multi-line when a persona /
    # project prefix is prepended) up to the AVAILABLE ROLES section, so keyword
    # routing sees the actual task, not just the first prefix line.
    out: list[str] = []
    capturing = False
    for line in content.splitlines():
        s = line.strip()
        if s.upper().startswith("AVAILABLE ROLES:"):
            break
        if capturing:
            out.append(line)
        elif s.upper().startswith("DIRECTIVE:"):
            capturing = True
            rest = line.split(":", 1)[1].strip()
            if rest:
                out.append(rest)
    return "\n".join(out).strip() if out else content.strip()


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

# Genuine "build" steps the demo reflector will recommend a skill for (word-boundary
# matched, so "implementation" in a review step does NOT trigger another synthesis).
_BUILD_VERBS = (
    "implement", "build", "write", "create", "compute", "calculate", "parse",
    "sort", "reverse", "generate", "encode", "decode", "convert", "format",
)
_SKILL_STOP = {
    "the", "a", "an", "of", "to", "and", "for", "with", "into", "from", "its",
    "this", "that", "on", "in", "at", "by",
}


def _first_field(content: str, label: str) -> str:
    for line in content.splitlines():
        if line.strip().upper().startswith(label.upper() + ":"):
            return line.split(":", 1)[1].strip()
    return content.strip()


# Small catalog of real, tested skills the offline demo can "synthesize" for common
# patterns. Keyed by substrings in the task; first match wins. A real model writes
# arbitrary skills — this just keeps the demo honest (the skill actually works) and
# varied (different tasks → different skills) instead of one hardcoded constant.
_SKILL_CATALOG = (
    (("reverse",), "reverse_string", "Reverse a sequence",
     "def run(s):\n    return s[::-1]\n",
     ['assert run("abc") == "cba"', "assert run([1, 2]) == [2, 1]"]),
    (("sum", "total", "add up"), "sum_numbers", "Sum a list of numbers",
     "def run(nums):\n    return sum(nums)\n",
     ["assert run([1, 2, 3]) == 6", "assert run([]) == 0"]),
    (("sort", "order"), "sort_list", "Sort a list ascending",
     "def run(xs):\n    return sorted(xs)\n",
     ["assert run([3, 1, 2]) == [1, 2, 3]", "assert run([]) == []"]),
    (("count", "length", "word"), "count_words", "Count whitespace-separated words",
     "def run(text):\n    return len(str(text).split())\n",
     ['assert run("a b c") == 3', 'assert run("") == 0']),
    (("upper", "capital"), "to_upper", "Uppercase a string",
     "def run(s):\n    return str(s).upper()\n",
     ['assert run("ab") == "AB"', 'assert run("") == ""']),
    (("slug", "url title"), "slugify", "Turn a title into a URL slug",
     "import re\n"
     "def run(text):\n"
     "    return re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')\n",
     ['assert run("Hello, World!") == "hello-world"', 'assert run("  A  B  ") == "a-b"']),
    (("roman", "numeral"), "roman_to_int", "Parse a Roman numeral to an integer",
     "def run(s):\n"
     "    vals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}\n"
     "    total = prev = 0\n"
     "    for ch in reversed(str(s).upper()):\n"
     "        v = vals.get(ch, 0)\n"
     "        total += -v if v < prev else v\n"
     "        prev = v\n"
     "    return total\n",
     ['assert run("XIV") == 14', 'assert run("MCMXCIV") == 1994']),
)


def _demo_skill(task: str) -> str:
    """Offline synthesis returns a small, real, *task-appropriate* skill — a known
    one for a recognizable pattern, otherwise a task-named passthrough helper."""
    low = task.lower()
    for keys, name, desc, code, tests in _SKILL_CATALOG:
        if any(k in low for k in keys):
            skill = {"name": name, "description": desc, "entrypoint": "run",
                     "caps": {"time_limit_s": 5}, "code": code, "tests": tests}
            return "```json\n" + json.dumps(skill) + "\n```"
    words = [w for w in re.findall(r"[a-z]+", low) if w not in _SKILL_STOP]
    name = "_".join(words[:2]) or "helper"
    skill = {
        "name": name,
        "description": f"(demo) reusable helper distilled from: {task[:60]}",
        "entrypoint": "run",
        "caps": {"time_limit_s": 5},
        "code": 'def run(value=None):\n    """(demo) sample skill synthesized offline."""\n    return value\n',
        "tests": ["assert run(1) == 1", "assert run('x') == 'x'", "assert run() is None"],
    }
    return "```json\n" + json.dumps(skill) + "\n```"


def _demo_canvas(directive: str) -> str:
    """A representative Canvas (A2UI) block so the generative-UI feature is visible
    offline. A real model emits a task-specific one; this is a fixed sample."""
    spec = {
        "title": "Overview",
        "blocks": [
            {"type": "callout", "tone": "info",
             "text": "Demo canvas — connect a real model and it renders structured, task-specific UI here."},
            {"type": "metric", "items": [
                {"label": "Options", "value": "2"},
                {"label": "Recommended", "value": "Option A"},
                {"label": "Confidence", "value": "High"},
            ]},
            {"type": "table", "columns": ["Criteria", "Option A", "Option B"],
             "rows": [["Performance", "High", "Medium"], ["Simplicity", "Medium", "High"], ["Cost", "$$", "$"]]},
            {"type": "chart", "kind": "bar", "labels": ["Perf", "Simplicity", "Cost"],
             "series": [{"name": "Option A", "data": [8, 6, 4]}, {"name": "Option B", "data": [6, 8, 7]}]},
        ],
    }
    return "```canvas\n" + json.dumps(spec) + "\n```"


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
        if "router for the glaux swarm" in sys:
            text = _router_plan(goal)
        elif "you review whether" in sys:
            task = _first_field(goal, "TASK")
            # Only recommend a skill for a genuine build step, and name the recommendation
            # after the task so the synthesized skill isn't a generic constant.
            if _has(task.lower(), _BUILD_VERBS):
                text = (
                    "```json\n"
                    '{"verdict": "accept", "reason": "meets the task (demo mode)", '
                    '"synthesize": ' + json.dumps(task) + "}\n```"
                )
            else:
                text = _ACCEPT
        elif "synthesize a reusable python skill" in sys:
            text = _demo_skill(_first_field(goal, "TASK"))
        elif "lead of the glaux swarm" in sys:
            # Final integration pass — return plain prose, not a JSON action.
            directive = _first_field(goal, "ORIGINAL REQUEST")
            text = (
                f"(demo) Here is the swarm's combined result for: {directive}\n\n"
                "Connect a real model (Ollama or a provider) for a full answer — "
                "in offline demo mode this just confirms every step ran and was verified."
            )
            low = directive.lower()
            if _has(low, _ANALYSIS_KW) or _has(low, _SCIENCE_KW) or "plan" in low or "design" in low:
                text += "\n\n" + _demo_canvas(directive)
        else:
            snippet = goal.splitlines()[0][:80] if goal else "the task"
            text = (
                "```json\n"
                f'{{"action": "finish", "result": "(demo) completed: {snippet}", "success": true}}\n'
                "```"
            )
        return LLMResponse(text=text, model_id=self.model_id, usage={}, raw=None)

    def stream(self, messages, *, system=None, temperature=0.0, max_tokens=1024, seed=None, on_delta=None):
        """Re-use complete() for the text, then 'type it out' word-by-word so the
        offline demo shows streaming. Any trailing ```canvas block is emitted whole."""
        import time

        resp = self.complete(messages, system=system, temperature=temperature, max_tokens=max_tokens, seed=seed)
        text = resp.text or ""
        if on_delta and text:
            cut = text.find("```canvas")
            prose = text if cut < 0 else text[:cut]
            for chunk in re.findall(r"\S+\s*", prose):
                on_delta(chunk)
                time.sleep(0.012)
            if cut >= 0:
                on_delta(text[cut:])
        return resp
