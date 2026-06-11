"""Phase 5 (backend): the FastAPI dashboard API, in offline demo mode."""

from __future__ import annotations

import pytest

pytest.importorskip("athena_ledger")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from core.api import STATE, app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_state():
    client.delete("/api/ledger")
    client.delete("/api/memory")
    STATE.eval_runs.clear()
    client.post("/api/safety", json={"mode": "live"})
    client.post("/api/approval", json={"mode": "auto"})
    yield
    client.post("/api/safety", json={"mode": "live"})
    client.post("/api/approval", json={"mode": "auto"})


def test_health_reports_demo_mode():
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert h["llm"] == "demo-offline"  # no API key in tests
    assert h["safety"] == "live"
    assert set(h["memory"]) == {"semantic", "episodic", "procedural"}


def test_dispatch_builds_a_verifiable_signed_chain():
    r = client.post("/api/task", json={"directive": "build a thing and summarize it"})
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["verification"]["valid"] is True
    # the plan and signed trace came back
    assert [s["role"] for s in data["plan"]] == ["coder", "researcher"]
    assert len(data["new_blocks"]) > 0
    types = {b["action_type"] for b in data["new_blocks"]}
    assert {"PLAN", "CALL_AGENT", "CAPABILITY_GRANT", "THINK"} <= types

    # ledger endpoint reflects the same chain and verifies
    led = client.get("/api/ledger").json()
    assert led["count"] == len(data["new_blocks"])
    assert led["verification"]["valid"] is True


def test_block_detail_and_404():
    client.post("/api/task", json={"directive": "do something"})
    b0 = client.get("/api/block/0").json()
    assert "signature" in b0 and "payload" in b0
    assert client.get("/api/block/99999").status_code == 404


def test_empty_directive_rejected():
    assert client.post("/api/task", json={"directive": "   "}).status_code == 400


# --- roster --------------------------------------------------------------


def test_agents_roster_exposes_identities():
    data = client.get("/api/agents").json()
    roles = {a["role"] for a in data["agents"]}
    assert roles == {"router", "coder", "researcher", "reflector"}
    for a in data["agents"]:
        # agent_id is base58(public key) — they match for a non-rotated identity
        assert a["agent_id"] == a["public_key"]
        assert a["namespace"] == "default"


# --- safety / kill switch ------------------------------------------------


def test_safety_get_and_set():
    assert client.get("/api/safety").json()["mode"] == "live"
    assert client.post("/api/safety", json={"mode": "halted"}).json()["mode"] == "halted"
    assert client.get("/api/safety").json()["mode"] == "halted"


def test_invalid_safety_mode_rejected():
    assert client.post("/api/safety", json={"mode": "banana"}).status_code == 400


def test_halted_dispatch_short_circuits_specialists():
    # baseline: a live dispatch produces specialist THINK blocks
    live = client.post("/api/task", json={"directive": "do real work"}).json()
    assert any(b["action_type"] == "THINK" for b in live["new_blocks"])

    client.delete("/api/ledger")
    client.post("/api/safety", json={"mode": "halted"})
    halted = client.post("/api/task", json={"directive": "do work while halted"}).json()
    # specialists short-circuit -> zero THINK blocks; the chain still verifies
    assert halted["verification"]["valid"] is True
    assert not any(b["action_type"] == "THINK" for b in halted["new_blocks"])


# --- memory --------------------------------------------------------------


def test_memory_add_list_search():
    add = client.post(
        "/api/memory/semantic", json={"text": "Athena signs every action with Ed25519"}
    ).json()
    assert add["count"] == 1

    listing = client.get("/api/memory/semantic").json()
    assert listing["layer"] == "semantic"
    assert any("Ed25519" in it["text"] for it in listing["items"])

    found = client.get("/api/memory/semantic", params={"q": "what signs actions"}).json()
    assert found["items"] and "Ed25519" in found["items"][0]["text"]


def test_memory_layers_are_isolated():
    client.post("/api/memory/semantic", json={"text": "a semantic fact about gravity"})
    client.post("/api/memory/episodic", json={"text": "deployed the service yesterday"})
    assert len(client.get("/api/memory/semantic").json()["items"]) == 1
    assert len(client.get("/api/memory/episodic").json()["items"]) == 1
    assert client.get("/api/memory/procedural").json()["items"] == []


def test_unknown_memory_layer_404():
    assert client.get("/api/memory/nonsense").status_code == 404


# --- cost / budget guard -------------------------------------------------


def test_dispatch_reports_cost():
    data = client.post("/api/task", json={"directive": "do a thing"}).json()
    assert data["cost"]["llm_calls"] > 0
    assert data["cost"]["total_tokens"] > 0
    assert data["budget_halt"] is None


def test_tight_budget_halts_dispatch():
    data = client.post(
        "/api/task",
        json={"directive": "do a multi-step thing", "budget": {"max_llm_calls": 1}},
    ).json()
    # router consumes the 1 allowed call; specialists are never dispatched
    assert data["budget_halt"] is not None
    assert data["cost"]["llm_calls"] == 1
    assert not any(s["accepted"] for s in data["steps"])


# --- skills (synthesis + curation) ---------------------------------------


def test_synthesize_stores_quarantined_skill():
    r = client.post("/api/skills/synthesize", json={"task": "reverse a string"}).json()
    assert r["ok"] is True
    assert r["stored"]["status"] == "quarantined"
    assert r["stored"]["name"] == "reverse_string"
    # it shows up in the library listing
    skills = client.get("/api/skills").json()["skills"]
    assert any(s["name"] == "reverse_string" for s in skills)


def test_skill_promotes_after_uses():
    synth = client.post("/api/skills/synthesize", json={"task": "reverse"}).json()
    sid = synth["stored"]["id"]
    last = None
    for _ in range(3):
        last = client.post(f"/api/skills/{sid}/use", json={"success": True}).json()
    assert last["status"] == "promoted"
    assert last["success_rate"] == 1.0


def test_use_unknown_skill_404():
    assert client.post("/api/skills/nope/use", json={"success": True}).status_code == 404


# --- eval harness --------------------------------------------------------


def test_eval_run_and_lift_from_synthesized_skill():
    # baseline: reverse_* cases fail (no skill), inline baselines pass
    base = client.post("/api/eval/run").json()
    base_passed = base["run"]["passed"]
    assert base["run"]["total"] >= 4
    assert any(not c["passed"] for c in base["run"]["cases"])  # reverse_* missing

    # synthesize the reverse_string skill, then re-run -> lift
    client.post("/api/skills/synthesize", json={"task": "reverse a string"})
    after = client.post("/api/eval/run").json()
    assert after["run"]["passed"] > base_passed
    assert after["lift"]["delta_pass_rate"] > 0
    assert "reverse_basic" in after["lift"]["newly_passing"]

    # run history is tracked
    runs = client.get("/api/eval/runs").json()["runs"]
    assert len(runs) >= 2


# --- autonomous synthesis + HITL gate ------------------------------------


def test_dispatch_autonomously_synthesizes_a_skill():
    data = client.post("/api/task", json={"directive": "build a function that reverses a string"}).json()
    assert data["synthesized"]  # reflector recommended a skill, swarm synthesized it
    assert any(s["ok"] for s in data["synthesized"])
    # in auto mode the non-sensitive skill is usable (quarantined), in the library
    skills = client.get("/api/skills").json()["skills"]
    assert any(s["name"] == "reverse_string" for s in skills)


def test_gated_mode_requires_approval_then_approve():
    client.post("/api/approval", json={"mode": "gated"})
    assert client.get("/api/approval").json()["mode"] == "gated"

    client.post("/api/task", json={"directive": "build a function that reverses a string"})
    pending = [s for s in client.get("/api/skills").json()["skills"] if s["status"] == "pending_approval"]
    assert pending  # held for approval

    approved = client.post(f"/api/skills/{pending[0]['id']}/approve").json()
    assert approved["status"] == "quarantined"


def test_invalid_approval_mode_rejected():
    assert client.post("/api/approval", json={"mode": "bogus"}).status_code == 400


def test_approve_nonexistent_skill_404():
    assert client.post("/api/skills/nope/approve").status_code == 404
