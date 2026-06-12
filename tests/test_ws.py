"""Live block streaming: ledger on_append hook + WebSocket fan-out."""

from __future__ import annotations

import pytest

pytest.importorskip("athena_ledger")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from core.api import app  # noqa: E402
from core.ledger import Ledger  # noqa: E402
from identity import AgentIdentity  # noqa: E402


def test_on_append_hook_fires_with_block():
    seen = []
    led = Ledger(on_append=seen.append)
    led.append(AgentIdentity.generate(), "THINK", {"x": 1})
    led.append(AgentIdentity.generate(), "EMIT_OBSERVATION", {"y": 2})
    assert len(seen) == 2
    assert seen[0]["action_type"] == "THINK"
    assert seen[1]["payload"] == {"y": 2}
    assert "signature" in seen[0] and "hash" in seen[0]


def test_on_append_failure_never_breaks_append():
    def boom(_block):
        raise RuntimeError("stream down")

    led = Ledger(on_append=boom)
    block = led.append(AgentIdentity.generate(), "THINK", {"x": 1})  # must not raise
    assert block["action_type"] == "THINK"
    assert led.verify().valid


def test_websocket_streams_blocks_during_dispatch():
    # context-managed client so startup runs and the WS loop is captured
    with TestClient(app) as c:
        with c.websocket_connect("/ws") as ws:
            c.delete("/api/ledger")
            c.post("/api/task", json={"directive": "do a small thing"})
            first = ws.receive_json()
            assert first["type"] == "block"
            assert first["block"]["action_type"] == "PLAN"  # router's plan is block 0
            assert "agent_id" in first["block"]
