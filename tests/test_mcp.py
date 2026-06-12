"""Phase 3.5: MCP tool client + agent CALL_MCP (signed)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("athena_ledger")

import safety  # noqa: E402
from agents import BaseAgent, LocalMCPClient, default_local_client  # noqa: E402
from agents.mcp import calc  # noqa: E402
from core.ledger import Ledger  # noqa: E402
from identity import AgentIdentity  # noqa: E402
from llm import ScriptedLLM  # noqa: E402


@pytest.fixture(autouse=True)
def _live():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


# --- client --------------------------------------------------------------


def test_local_client_list_and_call():
    c = default_local_client()
    names = {t.name for t in c.list_tools()}
    assert {"calc", "word_count", "uppercase"} <= names
    assert c.call_tool("calc", {"expression": "2 * (3 + 4)"}) == {"ok": True, "result": 14}
    assert c.call_tool("uppercase", {"text": "hi"}) == {"ok": True, "result": "HI"}


def test_unknown_tool():
    c = default_local_client()
    res = c.call_tool("nope", {})
    assert res["ok"] is False and "unknown tool" in res["error"]


def test_tool_error_surfaced():
    c = default_local_client()
    res = c.call_tool("calc", {"expression": "1 + "})  # syntax error
    assert res["ok"] is False and "error" in res


def test_calc_rejects_non_arithmetic():
    with pytest.raises(ValueError):
        calc("__import__('os').system('ls')")


def test_register_custom_tool():
    c = LocalMCPClient("test")
    c.register("double", "double a number", lambda n: n * 2, {"n": "number"})
    assert c.call_tool("double", {"n": 21}) == {"ok": True, "result": 42}


# --- agent integration ---------------------------------------------------


def _mcp(tool, **args):
    return f'```json\n{{"action": "call_mcp", "tool": "{tool}", "args": {json.dumps(args)}}}\n```'


def _finish(r):
    return f'```json\n{{"action": "finish", "result": "{r}", "success": true}}\n```'


def test_agent_calls_mcp_tool_and_logs_it():
    led = Ledger()
    identity = AgentIdentity.generate()
    llm = ScriptedLLM(responses=[_mcp("calc", expression="6 * 7"), _finish("42")])
    agent = BaseAgent(identity=identity, llm=llm, ledger=led, name="t", mcp_client=default_local_client())
    res = agent.run("compute 6 times 7")
    assert res.success
    # the tool ran and returned 42
    assert res.steps[0]["observation"] == {"ok": True, "result": 42}
    # the call was signed to the ledger as an MCP_TOOL action
    types = [b["action_type"] for b in led.blocks()]
    assert "MCP_TOOL" in types
    assert led.verify().valid


def test_agent_without_mcp_client_reports_error():
    llm = ScriptedLLM(responses=[_mcp("calc", expression="1+1"), _finish("done")])
    agent = BaseAgent(identity=AgentIdentity.generate(), llm=llm, name="t")  # no mcp_client
    res = agent.run("x")
    assert res.steps[0]["observation"]["ok"] is False
    assert "no MCP client" in res.steps[0]["observation"]["error"]


def test_mcp_skipped_in_dry_run():
    safety.set_mode("dry_run")
    llm = ScriptedLLM(responses=[_mcp("calc", expression="2+2"), _finish("done")])
    agent = BaseAgent(identity=AgentIdentity.generate(), llm=llm, name="t", mcp_client=default_local_client())
    res = agent.run("x")
    assert "dry-run" in str(res.steps[0]["observation"]["result"])
