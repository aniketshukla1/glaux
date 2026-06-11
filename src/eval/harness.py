"""Evaluation harness — measures whether the skill library actually works,
and whether self-improvement moves the needle.

A benchmark case names a skill (resolved from the library) or carries inline
code, plus inputs and an expected output. Each case runs in the Phase 0 sandbox
and is scored pass/fail. Runs are comparable: :func:`lift` reports which cases
newly pass/fail and the change in pass rate — so promoting a synthesized skill
shows up as measurable improvement.

Fully deterministic and offline (sandbox execution, exact-match scoring).
"""

from __future__ import annotations

import glob
import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from sandbox import Capabilities, run as sandbox_run


@dataclass
class CaseResult:
    name: str
    passed: bool
    expected: Any = None
    got: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    tags: list = field(default_factory=list)


@dataclass
class EvalRun:
    timestamp: float
    total: int
    passed: int
    cases: list = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 4),
            "cases": [asdict(c) for c in self.cases],
        }


def load_bench(directory) -> list[dict]:
    """Load benchmark cases from `<directory>/*.json`."""
    cases = []
    for path in sorted(glob.glob(os.path.join(str(directory), "*.json"))):
        with open(path) as f:
            cases.append(json.load(f))
    return cases


class EvalHarness:
    def __init__(self, library=None) -> None:
        self.library = library

    def _resolve(self, case: dict):
        """Return (code, entrypoint, caps) for a case, or (None, ...) if a named
        skill is missing from the library."""
        if "code" in case:
            return case["code"], case.get("entrypoint", "run"), case.get("caps", {})
        skill_name = case.get("skill")
        if skill_name and self.library is not None:
            for rec in self.library.list():
                if rec.name == skill_name:
                    return rec.code, rec.entrypoint, rec.caps
        return None, None, None

    def run_case(self, case: dict) -> CaseResult:
        expected = case.get("expected")
        tags = case.get("tags", [])
        code, entrypoint, caps = self._resolve(case)
        if code is None:
            return CaseResult(
                case["name"], False, expected, None,
                f"skill {case.get('skill')!r} not in library", 0.0, tags,
            )
        t0 = time.monotonic()
        res = sandbox_run(
            code,
            caps=Capabilities.from_dict(caps),
            inputs=case.get("args", {}),
            entrypoint=entrypoint,
        )
        duration_ms = (time.monotonic() - t0) * 1000.0
        if not res.ok:
            return CaseResult(
                case["name"], False, expected, None,
                res.error or res.killed_reason or "execution failed", duration_ms, tags,
            )
        got = res.return_value
        passed = got == expected
        return CaseResult(
            case["name"], passed, expected, got,
            None if passed else "output mismatch", duration_ms, tags,
        )

    def run_suite(self, cases: list[dict]) -> EvalRun:
        results = [self.run_case(c) for c in cases]
        passed = sum(1 for r in results if r.passed)
        return EvalRun(timestamp=time.time(), total=len(results), passed=passed, cases=results)


def lift(current: EvalRun, previous: Optional[EvalRun]) -> dict:
    """Regression/improvement delta vs. the previous run."""
    if previous is None:
        return {
            "delta_pass_rate": round(current.pass_rate, 4),
            "newly_passing": [],
            "newly_failing": [],
        }
    prev = {c.name: c.passed for c in previous.cases}
    newly_passing = [c.name for c in current.cases if c.passed and not prev.get(c.name, False)]
    newly_failing = [c.name for c in current.cases if not c.passed and prev.get(c.name, False)]
    return {
        "delta_pass_rate": round(current.pass_rate - previous.pass_rate, 4),
        "newly_passing": newly_passing,
        "newly_failing": newly_failing,
    }
