"""Phase 5 (backend): the FastAPI dashboard API, in offline demo mode."""

from __future__ import annotations

import pytest

pytest.importorskip("athena_ledger")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from core.api import STATE, app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_ledger():
    client.delete("/api/ledger")
    yield


def test_health_reports_demo_mode():
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert h["llm"] == "demo-offline"  # no API key in tests
    assert set(h["agents"]) == {"router", "coder", "researcher", "reflector"}


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
