"""Phase 3.2: swarm orchestration + capability-token-gated handoffs."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("athena_ledger")

import safety  # noqa: E402
from agents import (  # noqa: E402
    BaseAgent,
    HandoffRejected,
    Reflector,
    Router,
    Swarm,
    coder_agent,
    delegate,
    researcher_agent,
    topo_sort,
)
from agents.router import Step  # noqa: E402
from core.ledger import Ledger  # noqa: E402
from identity import AgentIdentity, CapabilityToken, issue_token  # noqa: E402
from llm import ScriptedLLM  # noqa: E402


@pytest.fixture(autouse=True)
def _live_mode():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


def _finish(result, success=True):
    return f'```json\n{{"action": "finish", "result": "{result}", "success": {str(success).lower()}}}\n```'


def _plain_agent(responses, name="t"):
    return BaseAgent(identity=AgentIdentity.generate(), llm=ScriptedLLM(responses=responses), name=name)


# --- capability-gated handoff (completes CALL_AGENT) ---------------------


def test_valid_handoff_runs_target_and_logs():
    caller = AgentIdentity.generate()
    target = _plain_agent([_finish("done")])
    led = Ledger()
    res = delegate(caller, target, "do it", capability="task:t", ledger=led)
    assert res.success and res.result == "done"
    types = [b["action_type"] for b in led.blocks()]
    assert "CALL_AGENT" in types and "CAPABILITY_GRANT" in types
    assert led.verify().valid


def test_handoff_rejects_token_for_other_subject():
    caller = AgentIdentity.generate()
    target = _plain_agent([_finish("x")])
    # token addressed to a different agent
    tok = issue_token(caller, AgentIdentity.generate().agent_id, "task:t", 300)
    with pytest.raises(HandoffRejected):
        target.accept_handoff(tok, caller.public_key_b58, "do it", capability="task:t")
    assert target.llm.calls == []  # never ran


def test_handoff_rejects_expired_token():
    caller = AgentIdentity.generate()
    target = _plain_agent([_finish("x")])
    tok = issue_token(caller, target.identity.agent_id, "task:t", -1)  # already expired
    with pytest.raises(HandoffRejected):
        target.accept_handoff(tok, caller.public_key_b58, "do it", capability="task:t")


def test_handoff_rejects_tampered_capability():
    caller = AgentIdentity.generate()
    target = _plain_agent([_finish("x")])
    tok = issue_token(caller, target.identity.agent_id, "task:t", 300)
    forged = CapabilityToken(
        issuer=tok.issuer,
        subject=tok.subject,
        capability="admin",  # escalated; signature no longer matches
        issued_at=tok.issued_at,
        expires_at=tok.expires_at,
        nonce=tok.nonce,
        signature=tok.signature,
    )
    with pytest.raises(HandoffRejected):
        target.accept_handoff(forged, caller.public_key_b58, "do it", capability="admin")


# --- router --------------------------------------------------------------


def test_router_parses_and_signs_plan():
    led = Ledger()
    plan_json = (
        '```json\n{"plan": ['
        '{"id": "s1", "role": "coder", "task": "write code", "depends_on": []},'
        '{"id": "s2", "role": "researcher", "task": "summarize", "depends_on": ["s1"]}'
        ']}\n```'
    )
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([plan_json]), ledger=led)
    plan = router.plan("build and summarize", roles=["coder", "researcher"])
    assert [s.id for s in plan.steps] == ["s1", "s2"]
    assert plan.steps[1].depends_on == ["s1"]
    assert any(b["action_type"] == "PLAN" for b in led.blocks())


def test_demo_router_emits_minimal_plans():
    from llm.demo import DemoLLM

    def roles_for(directive):
        r = Router(identity=AgentIdentity.generate(), llm=DemoLLM())
        return [s.role for s in r.plan(directive, roles=["coder", "researcher"]).steps]

    # a single specialist when one role covers it
    assert roles_for("Compute the sum of 12, 30 and 8") == ["coder"]
    assert roles_for("Reverse a string") == ["coder"]
    assert roles_for("Summarize how transformers work") == ["researcher"]
    assert roles_for("What is the capital of France?") == ["researcher"]
    # split only when the task has distinct do-it + explain-it phases
    assert roles_for("Reverse a string and explain how it works") == ["coder", "researcher"]


def test_topo_sort_orders_dependencies():
    steps = [
        Step("s2", "researcher", "summarize", ["s1"]),
        Step("s1", "coder", "code", []),
    ]
    order = [s.id for s in topo_sort(steps)]
    assert order == ["s1", "s2"]


def test_topo_sort_detects_cycle():
    steps = [Step("a", "x", "", ["b"]), Step("b", "y", "", ["a"])]
    with pytest.raises(ValueError):
        topo_sort(steps)


# --- reflector -----------------------------------------------------------


def test_reflector_accept_and_retry_verdicts():
    from agents import AgentResult

    accept_llm = ScriptedLLM(handler=lambda m, s: '```json\n{"verdict":"accept","reason":"ok"}\n```')
    refl = Reflector(identity=AgentIdentity.generate(), llm=accept_llm)
    assert refl.review("g", AgentResult(True, "r", [], 1)).accept

    retry_llm = ScriptedLLM(handler=lambda m, s: '```json\n{"verdict":"retry","reason":"wrong"}\n```')
    refl2 = Reflector(identity=AgentIdentity.generate(), llm=retry_llm)
    v = refl2.review("g", AgentResult(True, "r", [], 1))
    assert not v.accept and v.reason == "wrong"


# --- swarm end-to-end ----------------------------------------------------


def _swarm_plan(*steps):
    return "```json\n" + json.dumps({"plan": list(steps)}) + "\n```"


def test_swarm_runs_plan_with_handoffs_and_reflection():
    led = Ledger()
    plan = _swarm_plan(
        {"id": "s1", "role": "coder", "task": "write code", "depends_on": []},
        {"id": "s2", "role": "researcher", "task": "summarize", "depends_on": ["s1"]},
    )
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([plan]), ledger=led)
    coder = coder_agent(identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("code written")]), ledger=led)
    researcher = researcher_agent(
        identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("summary done")]), ledger=led
    )
    reflector = Reflector(
        identity=AgentIdentity.generate(),
        llm=ScriptedLLM(handler=lambda m, s: '```json\n{"verdict":"accept","reason":"ok"}\n```'),
        ledger=led,
    )
    swarm = Swarm(
        router=router,
        specialists={"coder": coder, "researcher": researcher},
        reflector=reflector,
        ledger=led,
    )
    res = swarm.run("build and summarize")
    assert res.success
    assert res.steps["s1"].accepted and res.steps["s2"].accepted
    assert res.final == "summary done"
    # one signed handoff per step
    assert sum(1 for b in led.blocks() if b["action_type"] == "CALL_AGENT") == 2
    # whole mixed-signer chain (router + specialists + reflector) verifies
    assert led.verify().valid


def test_swarm_retries_on_reflector_rejection():
    plan = _swarm_plan({"id": "s1", "role": "coder", "task": "tricky", "depends_on": []})
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([plan]))
    # coder must answer twice (one per attempt)
    coder = coder_agent(
        identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("attempt-1"), _finish("attempt-2")])
    )
    # reflector: retry, then accept
    reflector = Reflector(
        identity=AgentIdentity.generate(),
        llm=ScriptedLLM(
            responses=[
                '```json\n{"verdict":"retry","reason":"not yet"}\n```',
                '```json\n{"verdict":"accept","reason":"good now"}\n```',
            ]
        ),
    )
    swarm = Swarm(router=router, specialists={"coder": coder}, reflector=reflector, max_retries=1)
    res = swarm.run("do the tricky thing")
    assert res.success
    assert res.steps["s1"].attempts == 2
    assert res.final == "attempt-2"


def test_swarm_handles_unknown_role():
    plan = _swarm_plan({"id": "s1", "role": "ghost", "task": "x", "depends_on": []})
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([plan]))
    swarm = Swarm(router=router, specialists={"coder": _plain_agent([_finish("x")])})
    res = swarm.run("do x")
    assert not res.success
    assert not res.steps["s1"].accepted
