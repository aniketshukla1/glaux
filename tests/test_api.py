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
    client.post("/api/safety", json={"mode": "live"})
    yield
    client.post("/api/safety", json={"mode": "live"})


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
