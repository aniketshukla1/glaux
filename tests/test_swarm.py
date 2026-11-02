"""Phase 3.2: swarm orchestration + capability-token-gated handoffs."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("glaux_ledger")

import safety  # noqa: E402
from agents import (  # noqa: E402
    BaseAgent,
    HandoffRejected,
    Reflector,
    Router,
    Swarm,
    coder_agent,
    delegate,
    dependency_levels,
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


def test_demo_router_composes_teams_by_directive():
    """The offline demo router assembles a *team* that fits the directive, so the
    swarm exercises the full specialist roster rather than just coder/researcher."""
    from llm.demo import DemoLLM

    def roles_for(directive):
        r = Router(identity=AgentIdentity.generate(), llm=DemoLLM())
        return [s.role for s in r.plan(directive).steps]

    # a science question spins up a science lab (explain → write up)
    assert roles_for("Explain the mechanism of protein synthesis") == ["scientist", "writer"]
    # a systems build spins up an engineering pod (design → build → verify)
    assert roles_for("Design a scalable rate limiter architecture") == ["engineer", "coder", "tester"]
    # a comparison spins up the analysis desk
    assert roles_for("Compare PostgreSQL vs MongoDB and recommend one") == ["analyst", "writer"]
    # a plain build still pairs coder with a verifier
    assert roles_for("Reverse a string") == ["coder", "tester"]
    # later steps depend on earlier ones so context threads through
    plan = Router(identity=AgentIdentity.generate(), llm=DemoLLM()).plan(
        "Design a scalable rate limiter architecture"
    )
    assert plan.steps[1].depends_on == ["s1"]
    assert plan.steps[2].depends_on == ["s2"]


def test_swarm_stops_when_cancelled():
    led = Ledger()
    plan = _swarm_plan(
        {"id": "s1", "role": "coder", "task": "write code", "depends_on": []},
        {"id": "s2", "role": "researcher", "task": "summarize", "depends_on": ["s1"]},
    )
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([plan]), ledger=led)
    coder = coder_agent(identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("done")]), ledger=led)
    researcher = researcher_agent(identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("x")]), ledger=led)
    swarm = Swarm(router=router, specialists={"coder": coder, "researcher": researcher}, ledger=led)
    res = swarm.run("build and summarize", cancel=lambda: True)  # stop immediately
    assert res.cancelled and not res.success
    assert res.final == "Stopped."
    assert not res.steps  # nothing dispatched


def test_swarm_streams_final_answer():
    from llm.gateway import stream_complete  # noqa: F401 - smoke that the helper is importable
    led = Ledger()
    plan = _swarm_plan(
        {"id": "s1", "role": "coder", "task": "write code", "depends_on": []},
        {"id": "s2", "role": "researcher", "task": "summarize", "depends_on": ["s1"]},
    )
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([plan, "Integrated final answer."]), ledger=led)
    coder = coder_agent(identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("code")]), ledger=led)
    researcher = researcher_agent(identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("sum")]), ledger=led)
    swarm = Swarm(router=router, specialists={"coder": coder, "researcher": researcher}, ledger=led)
    tokens = []
    res = swarm.run("build and summarize", on_token=tokens.append)
    assert res.final == "Integrated final answer."
    # ScriptedLLM has no stream(), so the synthesis is delivered via the fallback
    assert "".join(tokens) == "Integrated final answer."


def test_demo_llm_streams_in_chunks():
    from llm.demo import DemoLLM
    from llm.gateway import Message
    chunks = []
    DemoLLM().stream([Message(role="user", content="ORIGINAL REQUEST: compare A and B")],
                     system="you are the lead of the glaux swarm", on_delta=chunks.append)
    assert len(chunks) > 1  # typed out word by word
    assert "".join(chunks).startswith("(demo)")


def test_agent_run_respects_cancel():
    from agents import BaseAgent

    agent = BaseAgent(identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("hi")]))
    res = agent.run("do it", cancel=lambda: True)
    assert not res.success and res.result == "stopped by user"


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
    # the router LLM is called twice: first to plan, then to integrate the final answer
    router = Router(
        identity=AgentIdentity.generate(),
        llm=ScriptedLLM([plan, "code written and summarized"]),
        ledger=led,
    )
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
    # the final answer integrates the team's work (not just the last step's output)
    assert res.final == "code written and summarized"
    # one signed handoff per step
    assert sum(1 for b in led.blocks() if b["action_type"] == "CALL_AGENT") == 2
    # whole mixed-signer chain (router + specialists + reflector) verifies
    assert led.verify().valid


def test_final_synthesis_tolerates_non_string_step_results():
    """A specialist that finishes with a structured (dict) result must not crash the
    final integration pass — it is stringified, and the run still succeeds."""
    led = Ledger()
    plan = _swarm_plan(
        {"id": "s1", "role": "coder", "task": "produce config", "depends_on": []},
        {"id": "s2", "role": "researcher", "task": "explain it", "depends_on": ["s1"]},
    )
    router = Router(
        identity=AgentIdentity.generate(),
        llm=ScriptedLLM([plan, "integrated answer"]),
        ledger=led,
    )
    # the coder finishes with a DICT result (the model returned structured JSON)
    dict_finish = '```json\n{"action": "finish", "result": {"key": "value"}, "success": true}\n```'
    coder = coder_agent(identity=AgentIdentity.generate(), llm=ScriptedLLM([dict_finish]), ledger=led)
    researcher = researcher_agent(
        identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("explained")]), ledger=led
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
        fast_replies=False,  # exercise the planned/reflected path
    )
    res = swarm.run("produce and explain")
    assert res.success
    assert isinstance(res.final, str)
    assert res.final == "integrated answer"


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
    swarm = Swarm(router=router, specialists={"coder": coder}, reflector=reflector, max_retries=1, fast_replies=False)
    res = swarm.run("do the tricky thing")
    assert res.success
    assert res.steps["s1"].attempts == 2
    assert res.final == "attempt-2"


def test_swarm_handles_unknown_role():
    plan = _swarm_plan({"id": "s1", "role": "ghost", "task": "x", "depends_on": []})
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([plan]))
    swarm = Swarm(router=router, specialists={"coder": _plain_agent([_finish("x")])}, fast_replies=False)
    res = swarm.run("do x")
    assert not res.success
    assert not res.steps["s1"].accepted


def test_dependency_levels_groups_independent_steps():
    steps = [
        Step("a", "researcher", "", []),
        Step("b", "researcher", "", []),
        Step("c", "researcher", "", ["a", "b"]),
    ]
    levels = dependency_levels(steps)
    assert [sorted(s.id for s in lv) for lv in levels] == [["a", "b"], ["c"]]


def test_independent_branches_run_concurrently():
    import time

    plan = _swarm_plan(
        {"id": "s1", "role": "coder", "task": "A", "depends_on": []},
        {"id": "s2", "role": "researcher", "task": "B", "depends_on": []},
    )
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([plan, "combined"]))
    delay = 0.4

    def slow(result):
        def handler(_messages, _system):
            time.sleep(delay)
            return _finish(result)

        return handler

    coder = BaseAgent(identity=AgentIdentity.generate(), llm=ScriptedLLM(handler=slow("a")), name="coder")
    researcher = BaseAgent(
        identity=AgentIdentity.generate(), llm=ScriptedLLM(handler=slow("b")), name="researcher"
    )
    swarm = Swarm(
        router=router, specialists={"coder": coder, "researcher": researcher}, fast_replies=False
    )
    t0 = time.monotonic()
    res = swarm.run("do two independent things")
    elapsed = time.monotonic() - t0
    assert res.success
    assert set(res.steps) == {"s1", "s2"}
    assert elapsed < 2 * delay  # ran concurrently, not back-to-back


def test_tiering_uses_primary_model_for_final_answer():
    # Under model tiering the router runs on a cheap/aux model, but the user-facing
    # final answer must come from the primary (synthesis_llm), not the aux model.
    led = Ledger()
    plan = _swarm_plan(
        {"id": "s1", "role": "coder", "task": "A", "depends_on": []},
        {"id": "s2", "role": "researcher", "task": "B", "depends_on": ["s1"]},
    )
    aux = ScriptedLLM([plan])  # only enough for router.plan — exhausted afterwards
    router = Router(identity=AgentIdentity.generate(), llm=aux, ledger=led)
    coder = coder_agent(identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("codeA")]), ledger=led)
    researcher = researcher_agent(
        identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish("resB")]), ledger=led
    )
    primary = ScriptedLLM(["INTEGRATED BY PRIMARY"])
    swarm = Swarm(
        router=router, specialists={"coder": coder, "researcher": researcher},
        ledger=led, fast_replies=False, synthesis_llm=primary,
    )
    res = swarm.run("build and summarize")
    assert res.success
    assert res.final == "INTEGRATED BY PRIMARY"  # not the aux model, not a fallback


def test_medium_tier_uses_generalist_without_planning_or_reflecting():
    # A non-trivial single-focus task (not simple, not a multi-phase team ask) goes
    # straight to the generalist: no router-planning call, no reflector, no team.
    def _boom(*_a, **_k):
        raise AssertionError("must not be called on the medium tier")

    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM(handler=_boom))
    reflector = Reflector(identity=AgentIdentity.generate(), llm=ScriptedLLM(handler=_boom))
    generalist = _plain_agent([_finish("refactored it")], name="generalist")
    swarm = Swarm(
        router=router,
        specialists={"coder": _plain_agent([_finish("unused")], name="coder")},
        reflector=reflector,
        responder=_plain_agent([_finish("unused")], name="responder"),
        generalist=generalist,
    )
    res = swarm.run("refactor this messy sorting helper to read cleanly")
    assert res.success
    assert res.final == "refactored it"
    assert list(res.steps) == ["s1"]


def test_medium_tier_off_for_multi_phase_task():
    # A clearly multi-phase (build + test) task still goes through the full swarm.
    plan = _swarm_plan(
        {"id": "s1", "role": "coder", "task": "build", "depends_on": []},
        {"id": "s2", "role": "tester", "task": "test", "depends_on": ["s1"]},
    )
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([plan, "shipped"]))
    generalist = _plain_agent([_finish("SHOULD NOT RUN")], name="generalist")
    swarm = Swarm(
        router=router,
        specialists={
            "coder": _plain_agent([_finish("built")], name="coder"),
            "tester": _plain_agent([_finish("tested")], name="tester"),
        },
        generalist=generalist,
    )
    res = swarm.run("build a queue and write tests for it")
    assert res.success
    assert res.final == "shipped"  # integrated by the swarm, not the generalist


def test_fast_path_answers_simple_query_without_planning_or_reflecting():
    # A plainly-simple query answers via the lean responder in one call: the
    # router's planning LLM call and the reflector are both skipped, and the
    # tool-carrying specialist is bypassed (all pure latency for a trivial Q).
    def _boom(*_a, **_k):
        raise AssertionError("must not be called on the fast path")

    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM(handler=_boom))
    reflector = Reflector(identity=AgentIdentity.generate(), llm=ScriptedLLM(handler=_boom))
    researcher = _plain_agent([_finish("via specialist (should be unused)")], name="researcher")
    responder = _plain_agent([_finish("A hash maps data to a fixed-size value.")], name="responder")
    swarm = Swarm(
        router=router, specialists={"researcher": researcher}, reflector=reflector, responder=responder
    )
    res = swarm.run("what is a hash function?")
    assert res.success
    assert "hash" in res.final.lower()
    assert list(res.steps) == ["s1"]
