"""Reflector-triggered autonomous synthesis + HITL approval gate."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("glaux_ledger")
pytest.importorskip("athenadb")

import safety  # noqa: E402
from agents import Reflector, Router, Swarm, coder_agent  # noqa: E402
from core.ledger import Ledger  # noqa: E402
from identity import AgentIdentity  # noqa: E402
from llm import ScriptedLLM  # noqa: E402
from memory import MemoryManager  # noqa: E402
from skills import PENDING_APPROVAL, QUARANTINED, REJECTED, SkillLibrary, SkillSynthesizer  # noqa: E402


@pytest.fixture(autouse=True)
def _live():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


def _finish(r="done"):
    return f'```json\n{{"action": "finish", "result": "{r}", "success": true}}\n```'


def _plan(role="coder"):
    return "```json\n" + json.dumps(
        {"plan": [{"id": "s1", "role": role, "task": "implement it", "depends_on": []}]}
    ) + "\n```"


def _reflect(synthesize=None):
    obj = {"verdict": "accept", "reason": "ok"}
    if synthesize:
        obj["synthesize"] = synthesize
    return "```json\n" + json.dumps(obj) + "\n```"


def _skill_json(caps=None):
    obj = {
        "name": "reverse_string",
        "description": "reverse",
        "entrypoint": "run",
        "caps": caps or {"time_limit_s": 5},
        "code": "def run(s):\n    return s[::-1]\n",
        "tests": ['assert run("ab") == "ba"'],
    }
    return "```json\n" + json.dumps(obj) + "\n```"


def _swarm(tmp_path, *, reflect_resp, skill_caps=None, require_approval=False):
    mm = MemoryManager(tmp_path / "db")
    lib = SkillLibrary(mm.procedural)
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([_plan()]))
    coder = coder_agent(identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish()]))
    reflector = Reflector(identity=AgentIdentity.generate(), llm=ScriptedLLM([reflect_resp]))
    synth = SkillSynthesizer(ScriptedLLM([_skill_json(skill_caps)]))
    swarm = Swarm(
        router=router,
        specialists={"coder": coder},
        reflector=reflector,
        synthesizer=synth,
        skill_library=lib,
        require_approval=require_approval,
    )
    return swarm, lib


# --- autonomous synthesis ------------------------------------------------


def test_reflector_recommendation_triggers_synthesis(tmp_path):
    swarm, lib = _swarm(tmp_path, reflect_resp=_reflect("a string reverser"))
    res = swarm.run("build a reverser")
    assert res.synthesized and res.synthesized[0]["ok"]
    assert res.synthesized[0]["status"] == QUARANTINED  # auto mode, non-sensitive
    assert len(lib.list()) == 1


def test_no_recommendation_no_synthesis(tmp_path):
    swarm, lib = _swarm(tmp_path, reflect_resp=_reflect(None))  # reflector accepts, no synth
    res = swarm.run("build a reverser")
    assert res.synthesized == []
    assert lib.list() == []


# --- HITL gate -----------------------------------------------------------


def test_gated_mode_holds_skill_for_approval(tmp_path):
    swarm, lib = _swarm(tmp_path, reflect_resp=_reflect("a reverser"), require_approval=True)
    res = swarm.run("build a reverser")
    assert res.synthesized[0]["status"] == PENDING_APPROVAL
    pending = lib.list(status=PENDING_APPROVAL)
    assert len(pending) == 1
    # human approves -> becomes usable (quarantined)
    approved = lib.approve(pending[0].id)
    assert approved.status == QUARANTINED


def test_sensitive_skill_requires_approval_even_in_auto(tmp_path):
    swarm, lib = _swarm(
        tmp_path,
        reflect_resp=_reflect("a network fetcher"),
        skill_caps={"net": True, "time_limit_s": 5},
        require_approval=False,  # auto mode...
    )
    res = swarm.run("build a fetcher")
    # ...but a net-capable (sensitive) skill is still gated
    assert res.synthesized[0]["sensitive"] is True
    assert res.synthesized[0]["status"] == PENDING_APPROVAL


def test_reject_pending_skill(tmp_path):
    swarm, lib = _swarm(tmp_path, reflect_resp=_reflect("a reverser"), require_approval=True)
    swarm.run("build a reverser")
    pending = lib.list(status=PENDING_APPROVAL)[0]
    rejected = lib.reject(pending.id)
    assert rejected.status == REJECTED
    assert lib.list(status=PENDING_APPROVAL) == []


# --- ledger trail --------------------------------------------------------


def test_synthesis_and_approval_logged_to_ledger(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    lib = SkillLibrary(mm.procedural)
    led = Ledger()
    router = Router(identity=AgentIdentity.generate(), llm=ScriptedLLM([_plan()]), ledger=led)
    coder = coder_agent(identity=AgentIdentity.generate(), llm=ScriptedLLM([_finish()]), ledger=led)
    reflector = Reflector(
        identity=AgentIdentity.generate(), llm=ScriptedLLM([_reflect("a reverser")]), ledger=led
    )
    swarm = Swarm(
        router=router,
        specialists={"coder": coder},
        reflector=reflector,
        ledger=led,
        synthesizer=SkillSynthesizer(ScriptedLLM([_skill_json()])),
        skill_library=lib,
        require_approval=True,
    )
    swarm.run("build a reverser")
    types = [b["action_type"] for b in led.blocks()]
    assert "SYNTHESIZE_SKILL" in types
    assert "REQUEST_APPROVAL" in types
    assert led.verify().valid