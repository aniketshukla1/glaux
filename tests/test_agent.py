"""Phase 3.1: BaseAgent ReAct loop — signing, sandboxed skills, safety,
checkpoints, reproducibility."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("glaux_ledger")

import safety  # noqa: E402
from agents import BaseAgent  # noqa: E402
from core.ledger import Ledger  # noqa: E402
from identity import AgentIdentity  # noqa: E402
from llm import ScriptedLLM  # noqa: E402


@pytest.fixture(autouse=True)
def _live_mode():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


def _finish(result, success=True):
    return f'```json\n{{"action": "finish", "result": "{result}", "success": {str(success).lower()}}}\n```'


def _call(skill_id, **args):
    return f'```json\n{{"action": "call_skill", "skill_id": "{skill_id}", "args": {json.dumps(args)}}}\n```'


def _agent(llm, **kw):
    return BaseAgent(identity=AgentIdentity.generate(), llm=llm, name="tester", **kw)


# --- basic loop ----------------------------------------------------------


def test_agent_finishes_immediately():
    agent = _agent(ScriptedLLM(responses=[_finish("the answer")]))
    res = agent.run("what is the answer")
    assert res.success
    assert res.result == "the answer"
    assert res.iterations == 1


def test_agent_calls_skill_then_finishes():
    skills = {
        "increment": {
            "code": "def run(x):\n    return x + 1\n",
            "caps": {"time_limit_s": 5},
            "name": "increment",
            "entrypoint": "run",
        }
    }
    llm = ScriptedLLM(responses=[_call("increment", x=41), _finish("42")])
    agent = _agent(llm)
    res = agent.run("increment 41", skills=skills)
    assert res.success
    # the skill ran in the sandbox and returned 42
    call_step = res.steps[0]
    assert call_step["observations"][0]["ok"] is True
    assert call_step["observations"][0]["return_value"] == 42


def test_unknown_skill_is_reported_not_crashed():
    llm = ScriptedLLM(responses=[_call("nope", x=1), _finish("recovered", success=False)])
    res = _agent(llm).run("do a thing", skills={})
    assert res.steps[0]["observations"][0]["ok"] is False
    assert "unknown skill" in res.steps[0]["observations"][0]["error"]


def test_repeated_failing_action_aborts():
    # qwen-style loop: keeps calling a skill that doesn't exist
    llm = ScriptedLLM(handler=lambda m, s: _call("slicing", x=1))
    res = _agent(llm, max_iterations=10).run("reverse a string", skills={})
    assert not res.success
    assert "aborted" in res.result
    assert res.iterations <= 3  # stopped by the loop guard, not after 10


def test_max_iterations_with_progress_but_no_finish():
    # calls a real skill every turn (progresses) but never finishes -> max iters
    skills = {"noop": {"code": "def run():\n    return 1\n", "caps": {}, "entrypoint": "run"}}
    llm = ScriptedLLM(handler=lambda m, s: _call("noop"))
    res = _agent(llm, max_iterations=3).run("loop", skills=skills)
    assert not res.success
    assert res.iterations == 3
    assert "max iterations" in res.result


# --- safety --------------------------------------------------------------


def test_halted_short_circuits_without_calling_llm():
    safety.set_mode("halted")
    llm = ScriptedLLM(responses=[_finish("should not run")])
    res = _agent(llm).run("anything")
    assert res.halted
    assert not res.success
    assert llm.calls == []  # the LLM was never invoked


# --- ledger integration --------------------------------------------------


def test_actions_are_signed_to_the_ledger():
    led = Ledger()
    identity = AgentIdentity.generate()
    skills = {"inc": {"code": "def run(x):\n    return x+1\n", "caps": {}, "name": "inc"}}
    llm = ScriptedLLM(responses=[_call("inc", x=1), _finish("2")])
    agent = BaseAgent(identity=identity, llm=llm, ledger=led, name="t")
    agent.run("increment", skills=skills)
    assert len(led) >= 4  # THINK, CALL_SKILL, OBSERVATION, THINK, OBSERVATION(finish)
    assert led.verify().valid
    assert all(b["agent_id"] == identity.agent_id for b in led.blocks())


# --- reproducibility envelope -------------------------------------------


def test_reproducibility_envelope():
    llm = ScriptedLLM(responses=[_call("x"), _finish("done")])
    res = _agent(llm, temperature=0.2, seed=7).run("task", skills={})
    repro = res.reproducibility
    assert repro["model_id"] == "scripted-v1"
    assert repro["temperature"] == 0.2
    assert repro["seed"] == 7
    assert len(repro["prompt_hashes"]) == res.iterations


# --- durable checkpointing ----------------------------------------------


def test_checkpoint_written(tmp_path):
    llm = ScriptedLLM(responses=[_call("x"), _finish("done")])
    agent = _agent(llm, checkpoint_dir=str(tmp_path))
    res = agent.run("task", task_id="job-1", skills={})
    cp = tmp_path / "job-1.json"
    assert cp.exists()
    state = json.loads(cp.read_text())
    assert state["goal"] == "task"
    assert state["iteration"] == res.iterations


def test_resume_from_checkpoint(tmp_path):
    # Pre-seed a checkpoint as if a prior run had completed one step.
    (tmp_path / "job-2.json").write_text(
        json.dumps(
            {
                "goal": "task",
                "iteration": 1,
                "scratchpad": [
                    {"iteration": 0, "thought": "prior", "action": None, "observation": {"note": "x"}}
                ],
            }
        )
    )
    llm = ScriptedLLM(responses=[_finish("resumed")])
    agent = _agent(llm, checkpoint_dir=str(tmp_path))
    res = agent.run("task", task_id="job-2", skills={}, resume=True)
    assert res.success
    # the resumed run kept the prior step and only made one new LLM call
    assert len(llm.calls) == 1
    assert res.steps[0]["thought"] == "prior"
