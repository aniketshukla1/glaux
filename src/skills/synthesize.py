"""Skill synthesis pipeline (the Voyager-style self-improvement step).

Given a task, an LLM proposes a reusable skill *and* its tests. We statically
cap-check the code, then run each test in the Phase 0 sandbox under the skill's
declared capabilities. Only skills whose tests pass (and whose code stays within
its caps) are returned for storage — where the library quarantines them until
they prove themselves in real use.

Offline-testable: a ScriptedLLM/DemoLLM returns a canned skill+tests JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agents.budget import BudgetTracker, charge_for_response
from agents.protocol import extract_json
from llm.gateway import LLMClient, Message
from sandbox import Capabilities, run as sandbox_run

from .capcheck import static_cap_check

SYNTH_SYSTEM = """You synthesize a reusable Python skill for the Athena swarm.
Given a task, respond with a single JSON object in a ```json block:
{
  "name": "<snake_case_name>",
  "description": "<one line>",
  "entrypoint": "run",
  "caps": {"net": false, "fs_write": [], "time_limit_s": 5},
  "code": "def run(...):\\n    ...\\n",
  "tests": ["assert run(...) == ...", "assert run(...) == ..."]
}
The code must define the entrypoint function. Each test is a standalone Python
snippet that calls the entrypoint and asserts. Declare the minimum capabilities;
default to no network and no filesystem writes."""


@dataclass
class SkillCandidate:
    name: str
    description: str
    code: str
    entrypoint: str = "run"
    caps: dict = field(default_factory=dict)
    tests: list[str] = field(default_factory=list)


@dataclass
class SynthesisResult:
    ok: bool
    reason: str = ""
    candidate: Optional[SkillCandidate] = None
    cap_violations: list[str] = field(default_factory=list)
    test_results: list[dict] = field(default_factory=list)

    @property
    def tests_passed(self) -> bool:
        return bool(self.test_results) and all(t["ok"] for t in self.test_results)


class SkillSynthesizer:
    def __init__(self, llm: LLMClient, *, temperature: float = 0.0, max_tokens: int = 1500) -> None:
        self.llm = llm
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.budget: Optional[BudgetTracker] = None  # set by the Swarm per task

    def synthesize(self, task: str) -> SynthesisResult:
        messages = [Message(role="user", content=f"TASK: {task}")]
        resp = self.llm.complete(
            messages,
            system=SYNTH_SYSTEM,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        charge_for_response(self.budget, resp, SYNTH_SYSTEM, messages)
        data = extract_json(resp.text)
        if not isinstance(data, dict) or "code" not in data:
            return SynthesisResult(False, "LLM did not return a valid skill JSON")

        candidate = SkillCandidate(
            name=str(data.get("name", "unnamed_skill")),
            description=str(data.get("description", "")),
            code=str(data["code"]),
            entrypoint=str(data.get("entrypoint", "run")),
            caps=data.get("caps") or {},
            tests=[str(t) for t in (data.get("tests") or [])],
        )

        violations = static_cap_check(candidate.code, candidate.caps)
        if violations:
            return SynthesisResult(
                False, "code exceeds declared capabilities", candidate, cap_violations=violations
            )

        if not candidate.tests:
            return SynthesisResult(False, "no tests synthesized", candidate)

        results = self._run_tests(candidate)
        result = SynthesisResult(False, "", candidate, test_results=results)
        if result.tests_passed:
            result.ok = True
            result.reason = "tests passed"
        else:
            result.reason = "one or more tests failed"
        return result

    def _run_tests(self, candidate: SkillCandidate) -> list[dict]:
        caps = Capabilities.from_dict(candidate.caps)
        results = []
        for i, test in enumerate(candidate.tests):
            program = candidate.code + "\n\n" + test + "\n"
            res = sandbox_run(program, caps=caps)
            results.append(
                {"index": i, "ok": res.ok, "error": res.error, "killed_reason": res.killed_reason}
            )
        return results
