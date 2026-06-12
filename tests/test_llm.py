"""Phase 3.1: LLM gateway seam + action protocol parsing."""

from __future__ import annotations

from agents.protocol import parse_action
from llm import Message, ScriptedLLM


def test_scripted_llm_returns_in_order_and_records_calls():
    llm = ScriptedLLM(responses=["first", "second"])
    r1 = llm.complete([Message("user", "hi")], system="sys")
    r2 = llm.complete([Message("user", "again")])
    assert r1.text == "first"
    assert r2.text == "second"
    assert r1.model_id == "scripted-v1"
    assert len(llm.calls) == 2
    assert llm.calls[0]["system"] == "sys"


def test_scripted_llm_handler():
    llm = ScriptedLLM(handler=lambda messages, system: f"echo:{messages[-1].content}")
    assert llm.complete([Message("user", "ping")]).text == "echo:ping"


def test_parse_fenced_action():
    text = 'Reasoning here.\n```json\n{"action": "finish", "result": "done"}\n```'
    action = parse_action(text)
    assert action == {"action": "finish", "result": "done"}


def test_parse_bare_object_with_nesting():
    text = 'I will call it. {"action": "call_skill", "skill_id": "s", "args": {"x": {"y": 1}}}'
    action = parse_action(text)
    assert action["action"] == "call_skill"
    assert action["args"] == {"x": {"y": 1}}


def test_parse_returns_none_without_action_key():
    assert parse_action("just prose, no json") is None
    assert parse_action('{"not_an_action": 1}') is None


def test_parse_prefers_fenced_block():
    text = '{"action": "finish", "result": "bare"}\n```json\n{"action": "finish", "result": "fenced"}\n```'
    assert parse_action(text)["result"] == "fenced"


def test_parse_repairs_small_model_json_defects():
    from agents.protocol import extract_json

    # stray empty parens (seen from qwen2.5) + nested objects in a fenced block
    text = '```json\n{"plan": [{"id": "s1", "depends_on": []}, {"id": "s2", "depends_on": ["s1"]()}]}\n```'
    obj = extract_json(text)
    assert obj is not None
    assert [s["id"] for s in obj["plan"]] == ["s1", "s2"]


def test_parse_repairs_trailing_comma():
    from agents.protocol import extract_json

    assert extract_json('{"action": "finish", "result": "x",}')["result"] == "x"
