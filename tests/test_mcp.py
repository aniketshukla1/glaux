"""Phase 3.5: MCP tool client + agent CALL_MCP (signed)."""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

pytest.importorskip("glaux_ledger")

import safety  # noqa: E402
from agents import (  # noqa: E402
    BaseAgent,
    LocalMCPClient,
    MCPRegistry,
    MCPServerConfig,
    StdioMCPClient,
    default_local_client,
)
from agents.mcp import _tool_result_to_obs, calc  # noqa: E402
from core.ledger import Ledger  # noqa: E402
from identity import AgentIdentity  # noqa: E402
from llm import ScriptedLLM  # noqa: E402

FAKE_SERVER = pathlib.Path(__file__).parent / "fixtures" / "fake_mcp_server.py"


def _stdio_cfg(name: str = "fake") -> MCPServerConfig:
    return MCPServerConfig(name=name, transport="stdio", command=sys.executable, args=[str(FAKE_SERVER)])


@pytest.fixture(autouse=True)
def _live():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


# --- client --------------------------------------------------------------


def test_local_client_list_and_call():
    c = default_local_client()
    names = {t.name for t in c.list_tools()}
    assert {"calc", "format_json", "text_stats", "regex_extract", "hash_text"} <= names
    assert c.call_tool("calc", {"expression": "2 * (3 + 4)"}) == {"ok": True, "result": 14}
    assert c.call_tool("text_stats", {"text": "one two three"})["result"]["words"] == 3


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
    assert res.steps[0]["observations"][0] == {"ok": True, "result": 42}
    # the call was signed to the ledger as an MCP_TOOL action
    types = [b["action_type"] for b in led.blocks()]
    assert "MCP_TOOL" in types
    assert led.verify().valid


def test_agent_without_mcp_client_reports_error():
    llm = ScriptedLLM(responses=[_mcp("calc", expression="1+1"), _finish("done")])
    agent = BaseAgent(identity=AgentIdentity.generate(), llm=llm, name="t")  # no mcp_client
    res = agent.run("x")
    assert res.steps[0]["observations"][0]["ok"] is False
    assert "no MCP client" in res.steps[0]["observations"][0]["error"]


def test_batched_tool_calls_run_concurrently():
    import time

    client = LocalMCPClient("slow")
    client.register("slow", "slow echo", lambda x: (time.sleep(0.4) or x), {"x": "number"})
    # one turn emits two INDEPENDENT tool calls -> they run in parallel
    batch = (
        '```json\n{"actions": ['
        '{"action": "call_mcp", "tool": "slow", "args": {"x": 1}}, '
        '{"action": "call_mcp", "tool": "slow", "args": {"x": 2}}'
        ']}\n```'
    )
    llm = ScriptedLLM(responses=[batch, _finish("done")])
    agent = BaseAgent(identity=AgentIdentity.generate(), llm=llm, name="t", mcp_client=client)
    t0 = time.monotonic()
    res = agent.run("run both tools")
    elapsed = time.monotonic() - t0
    assert res.success
    obs = res.steps[0]["observations"]
    assert len(obs) == 2 and all(o["ok"] for o in obs)  # both ran, in one turn
    assert {o["result"] for o in obs} == {1, 2}
    assert elapsed < 0.8  # 2 x 0.4s concurrently, not 0.8s back-to-back


def test_mcp_skipped_in_dry_run():
    safety.set_mode("dry_run")
    llm = ScriptedLLM(responses=[_mcp("calc", expression="2+2"), _finish("done")])
    agent = BaseAgent(identity=AgentIdentity.generate(), llm=llm, name="t", mcp_client=default_local_client())
    res = agent.run("x")
    assert "dry-run" in str(res.steps[0]["observations"][0]["result"])


# --- real stdio MCP server -----------------------------------------------


def test_stdio_client_connects_and_lists_tools():
    c = StdioMCPClient(_stdio_cfg())
    c.connect()
    try:
        assert c.status == "connected"
        assert {t.name for t in c.list_tools()} >= {"echo", "add"}
        # tool metadata comes from the server's inputSchema
        echo = next(t for t in c.list_tools() if t.name == "echo")
        assert echo.input_schema.get("type") == "object"
    finally:
        c.close()


def test_stdio_client_calls_tools():
    c = StdioMCPClient(_stdio_cfg())
    c.connect()
    try:
        assert c.call_tool("echo", {"text": "hi"}) == {"ok": True, "result": "hi"}
        assert c.call_tool("add", {"a": 2, "b": 3}) == {"ok": True, "result": "5"}
        bad = c.call_tool("nope", {})
        assert bad["ok"] is False
    finally:
        c.close()


def test_stdio_client_bad_command_marks_error():
    c = StdioMCPClient(MCPServerConfig(name="x", transport="stdio", command="definitely-not-a-real-binary-xyz"))
    with pytest.raises(Exception):
        c.connect()
    assert c.status == "error" and c.error


# --- registry ------------------------------------------------------------


def test_registry_aggregates_builtin_and_server(tmp_path):
    reg = MCPRegistry(builtin=default_local_client(), config_path=tmp_path / "mcp.json")
    reg.add_server(_stdio_cfg())
    try:
        names = {t.name for t in reg.list_tools()}
        assert {"calc", "echo", "add"} <= names  # builtin + connected server
        assert reg.call_tool("calc", {"expression": "2+2"}) == {"ok": True, "result": 4}
        assert reg.call_tool("echo", {"text": "yo"}) == {"ok": True, "result": "yo"}
        assert (tmp_path / "mcp.json").exists()  # persisted on add
        status = reg.server_status("fake")
        assert status["status"] == "connected" and status["tool_count"] >= 2
    finally:
        reg.close_all()


def test_registry_remove_server(tmp_path):
    reg = MCPRegistry(config_path=tmp_path / "mcp.json")
    reg.add_server(_stdio_cfg())
    assert "echo" in {t.name for t in reg.list_tools()}
    reg.remove_server("fake")
    assert "echo" not in {t.name for t in reg.list_tools()}
    assert reg.statuses() == []


def test_registry_persistence_roundtrip(tmp_path):
    path = tmp_path / "mcp.json"
    reg = MCPRegistry(config_path=path)
    reg.add_server(_stdio_cfg(), connect=False)  # config saved, no process
    reg.close_all()

    reg2 = MCPRegistry(config_path=path)
    reg2.load(connect=True)
    try:
        assert "fake" in {s["name"] for s in reg2.statuses()}
        assert {t.name for t in reg2.list_tools()} >= {"echo", "add"}
    finally:
        reg2.close_all()


def test_registry_unknown_tool_lists_available(tmp_path):
    reg = MCPRegistry(builtin=default_local_client(), config_path=tmp_path / "mcp.json")
    res = reg.call_tool("ghost", {})
    assert res["ok"] is False and "unknown tool" in res["error"]
    assert "calc" in res["error"]


# --- result flattening ---------------------------------------------------


def test_tool_result_flattening():
    assert _tool_result_to_obs({"content": [{"type": "text", "text": "x"}]}) == {"ok": True, "result": "x"}
    err = _tool_result_to_obs({"content": [{"type": "text", "text": "boom"}], "isError": True})
    assert err["ok"] is False and err["error"] == "boom"
    assert _tool_result_to_obs({"structuredContent": {"n": 5}, "content": []}) == {"ok": True, "result": {"n": 5}}
