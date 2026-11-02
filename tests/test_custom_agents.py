"""User-defined sub-agents: custom specialists merged into the router's roster."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.custom_agents import CustomAgentError, CustomAgents, build_custom_specialists  # noqa: E402


def test_save_list_get_delete(tmp_path):
    ca = CustomAgents(path=tmp_path / "subagents.json")
    r = ca.save("Deploy Bot", "ships releases", "You are Deploy Bot.", iterations=5)
    assert r["slug"] == "deploy-bot" and r["iterations"] == 5
    assert ca.list() == [
        {"name": "Deploy Bot", "description": "ships releases", "prompt": "You are Deploy Bot.", "iterations": 5, "slug": "deploy-bot"}
    ]
    assert ca.get("deploy-bot")["prompt"] == "You are Deploy Bot."
    ca.delete("Deploy Bot")
    assert ca.list() == []


def test_persistence_across_instances(tmp_path):
    p = tmp_path / "subagents.json"
    CustomAgents(path=p).save("X", "d", "prompt")
    assert CustomAgents(path=p).get("x")["name"] == "X"


def test_validation(tmp_path):
    ca = CustomAgents(path=tmp_path / "s.json")
    with pytest.raises(CustomAgentError):
        ca.save("", "d", "p")  # no name
    with pytest.raises(CustomAgentError):
        ca.save("ok", "d", "   ")  # no prompt
    with pytest.raises(CustomAgentError):
        ca.save("ok", "d", "x" * 8001)  # prompt too long


def test_iterations_clamped(tmp_path):
    ca = CustomAgents(path=tmp_path / "s.json")
    assert ca.save("a", "", "p", iterations=999)["iterations"] == 20
    assert ca.save("b", "", "p", iterations=0)["iterations"] == 1
    assert ca.save("c", "", "p", iterations="bad")["iterations"] == 8


def test_build_merges_named_agent_and_skips_reserved(tmp_path):
    pytest.importorskip("glaux_ledger")
    from identity import AgentIdentity
    from llm import ScriptedLLM

    ca = CustomAgents(path=tmp_path / "s.json")
    ca.save("Deploy Bot", "ships releases", "You are Deploy Bot.")
    ca.save("researcher", "should be skipped", "shadowing prompt")  # collides with a built-in role
    identities = {"deploy-bot": AgentIdentity.generate(), "researcher": AgentIdentity.generate()}
    built = build_custom_specialists(
        ca, identities=identities, llm=ScriptedLLM(responses=[]), reserved={"researcher"}
    )
    assert set(built) == {"deploy-bot"}  # the reserved-name one is skipped
    agent = built["deploy-bot"]
    assert agent.description == "ships releases"  # router reads this
    assert agent.name == "deploy-bot"
    assert "You are Deploy Bot." in agent.system_prompt


def test_build_skips_agents_without_a_minted_identity(tmp_path):
    pytest.importorskip("glaux_ledger")
    from llm import ScriptedLLM

    ca = CustomAgents(path=tmp_path / "s.json")
    ca.save("no-id", "d", "p")
    built = build_custom_specialists(ca, identities={}, llm=ScriptedLLM(responses=[]), reserved=set())
    assert built == {}
