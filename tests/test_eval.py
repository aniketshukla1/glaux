"""Phase 4.3: evaluation harness — scoring, library resolution, and lift."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("athenadb")

import safety  # noqa: E402
from eval import EvalHarness, lift, load_bench  # noqa: E402
from llm import ScriptedLLM  # noqa: E402
from memory import MemoryManager  # noqa: E402
from skills import SkillLibrary, SkillSynthesizer  # noqa: E402

# inline (self-contained) cases — always runnable
INLINE = [
    {"name": "sum", "code": "def run(xs):\n    return sum(xs)\n", "args": {"xs": [1, 2, 3]}, "expected": 6},
    {"name": "square", "code": "def run(n):\n    return n * n\n", "args": {"n": 5}, "expected": 25},
]
# a case that needs the reverse_string skill from the library
SKILL_CASE = {"name": "reverse", "skill": "reverse_string", "args": {"s": "abc"}, "expected": "cba"}


@pytest.fixture(autouse=True)
def _live():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


def _reverse_skill_json():
    obj = {
        "name": "reverse_string",
        "description": "reverse",
        "entrypoint": "run",
        "caps": {"time_limit_s": 5},
        "code": "def run(s):\n    return s[::-1]\n",
        "tests": ['assert run("ab") == "ba"'],
    }
    return "```json\n" + json.dumps(obj) + "\n```"


def test_inline_cases_pass():
    run = EvalHarness().run_suite(INLINE)
    assert run.total == 2
    assert run.passed == 2
    assert run.pass_rate == 1.0


def test_failing_case_is_caught():
    run = EvalHarness().run_suite(
        [{"name": "wrong", "code": "def run():\n    return 1\n", "args": {}, "expected": 2}]
    )
    assert run.passed == 0
    assert run.cases[0].error == "output mismatch"
    assert run.cases[0].got == 1


def test_missing_skill_fails_case(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    harness = EvalHarness(SkillLibrary(mm.procedural))
    run = harness.run_suite([SKILL_CASE])
    assert run.passed == 0
    assert "not in library" in run.cases[0].error


def test_synthesized_skill_makes_case_pass(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    lib = SkillLibrary(mm.procedural)
    harness = EvalHarness(lib)

    before = harness.run_suite([SKILL_CASE] + INLINE)
    assert before.passed == 2  # only the 2 inline cases

    cand = SkillSynthesizer(ScriptedLLM([_reverse_skill_json()])).synthesize("reverse").candidate
    lib.add_candidate(cand)

    after = harness.run_suite([SKILL_CASE] + INLINE)
    assert after.passed == 3  # reverse now passes too

    delta = lift(after, before)
    assert delta["delta_pass_rate"] > 0
    assert delta["newly_passing"] == ["reverse"]
    assert delta["newly_failing"] == []


def test_lift_with_no_previous_run():
    run = EvalHarness().run_suite(INLINE)
    delta = lift(run, None)
    assert delta["delta_pass_rate"] == 1.0
    assert delta["newly_passing"] == []


def test_load_bench_reads_repo_suite():
    from pathlib import Path

    repo_bench = Path(__file__).resolve().parents[1] / "bench"
    cases = load_bench(repo_bench)
    names = {c["name"] for c in cases}
    assert {"slugify", "roman_numeral", "sum_list", "is_palindrome"} <= names
