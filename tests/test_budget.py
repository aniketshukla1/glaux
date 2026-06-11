"""Cost/budget guard: tracker math + agent/swarm enforcement."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("athena_ledger")

import safety  # noqa: E402
from agents import BaseAgent, Budget, BudgetTracker, Reflector, Router, Swarm, coder_agent  # noqa: E402
from agents.budget import charge_for_response, estimate_tokens  # noqa: E402
from identity import AgentIdentity  # noqa: E402
from llm import ScriptedLLM  # noqa: E402
from llm.gateway import LLMResponse, Message  # noqa: E402


@pytest.fixture(autouse=True)
def _live():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


def _finish(r="ok"):
    return f'```json\n{{"action": "finish", "result": "{r}", "success": true}}\n```'


def _call(skill_id):
    return f'```json\n{{"action": "call_skill", "skill_id": "{skill_id}", "args": {{}}}}\n```'


# --- tracker -------------------------------------------------------------


def test_tracker_charges_and_snapshots():
    t = BudgetTracker(Budget(max_llm_calls=3))
    t.charge("claude-sonnet-4-6", 1000, 500)
    assert t.total_tokens == 1500
    assert t.llm_calls == 1
    assert t.usd > 0
    assert t.snapshot()["total_tokens"] == 1500


def test_exceeded_by_each_limit():
    t = BudgetTracker(Budget(max_tokens=100))
    assert t.exceeded() is None
    t.charge("m", 80, 40)  # 120 >= 100
    assert "token budget" in t.exceeded()

    t2 = BudgetTracker(Budget(max_llm_calls=1))
    t2.charge("m", 1, 1)
    assert "call budget" in t2.exceeded()


def test_charge_estimates_when_usage_absent():
    t = BudgetTracker(Budget())
    resp = LLMResponse(text="x" * 40, model_id="m", usage={})
    charge_for_response(t, resp, "sys", [Message("user", "y" * 40)])
    # ~ (3+10) input + 10 output estimate
    assert t.total_tokens > 0
    assert t.llm_calls == 1


# --- agent enforcement ---------------------------------------------------


def test_agent_halts_when_call_budget_exhausted():
    # handler always loops (calls an unknown skill), never finishes
    llm = ScriptedLLM(handler=lambda m, s: _call("ghost"))
    tracker = BudgetTracker(Budget(max_llm_calls=2))
    agent = BaseAgent(
        identity=AgentIdentity.generate(), llm=llm, name="t", max_iterations=10, budget=tracker
    )
    res = agent.run("loop", skills={})
    assert not res.success
    assert "budget" in res.result
    assert res.cost["llm_calls"] == 2  # stopped at the limit, not 10


def test_agent_reports_cost_on_success():
    llm = ScriptedLLM(responses=[_finish("done")])
    tracker = BudgetTracker(Budget())
    agent = BaseAgent(identity=AgentIdentity.generate(), llm=llm, name="t", budget=tracker)
    res = agent.run("quick task", skills={})
    assert res.success
    assert res.cost["llm_calls"] == 1
    assert res.cost["total_tokens"] > 0


def test_no_budget_means_empty_cost():
    agent = BaseAgent(identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish()]), name="t")
    assert agent.run("x", skills={}).cost == {}


# --- swarm aggregation ---------------------------------------------------


def _plan(*steps):
    return "```json\n" + json.dumps({"plan": list(steps)}) + "\n```"


def test_swarm_aggregates_cost_across_agents():
    plan = _plan({"id": "s1", "role": "coder", "task": "do", "depends_on": []})
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([plan]))
    coder = coder_agent(identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("done")]))
    reflector = Reflector(
        identity=AgentIdentity.generate(),
        llm=ScriptedLLM(handler=lambda m, s: '```json\n{"verdict":"accept","reason":"ok"}\n```'),
    )
    swarm = Swarm(router=router, specialists={"coder": coder}, reflector=reflector)
    res = swarm.run("build it")
    # router + coder + reflector each made one charged call
    assert res.cost["llm_calls"] == 3
    assert res.cost["total_tokens"] > 0
    assert res.budget_halt is None


def test_swarm_stops_dispatching_when_budget_hit():
    plan = _plan(
        {"id": "s1", "role": "coder", "task": "a", "depends_on": []},
        {"id": "s2", "role": "coder", "task": "b", "depends_on": ["s1"]},
    )
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([plan]))
    coder = coder_agent(
        identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("a"), _finish("b")])
    )
    # budget of 2 LLM calls: router(1) + step1 coder(1) -> step2 is skipped
    swarm = Swarm(router=router, specialists={"coder": coder})
    res = swarm.run("two steps", budget=Budget(max_llm_calls=2))
    assert res.budget_halt is not None
    assert res.steps["s2"].attempts == 0  # never dispatched
