"""Authored playbooks: markdown instructions the swarm can consult on demand."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.mcp import LocalMCPClient  # noqa: E402
from agents.playbook import (  # noqa: E402
    PlaybookError,
    Playbooks,
    register_playbooks,
    unregister_playbooks,
)


def test_save_list_read_roundtrip(tmp_path):
    pb = Playbooks(root=tmp_path)
    r = pb.save("Deploy Checklist", "steps to ship", "1. run tests\n2. tag release")
    assert r["slug"] == "deploy-checklist" and r["name"] == "Deploy Checklist"
    assert pb.list() == [
        {"name": "Deploy Checklist", "slug": "deploy-checklist", "description": "steps to ship"}
    ]
    doc = pb.read("Deploy Checklist")
    assert doc["description"] == "steps to ship"
    assert doc["body"] == "1. run tests\n2. tag release"


def test_read_by_slug_or_display_name(tmp_path):
    pb = Playbooks(root=tmp_path)
    pb.save("My Playbook", "d", "body")
    assert pb.read("my-playbook")["body"] == "body"
    assert pb.read("My Playbook")["body"] == "body"


def test_missing_playbook_errors(tmp_path):
    pb = Playbooks(root=tmp_path)
    with pytest.raises(PlaybookError):
        pb.read("nope")


def test_empty_or_symbol_only_name_rejected(tmp_path):
    pb = Playbooks(root=tmp_path)
    with pytest.raises(PlaybookError):
        pb.save("   ", "d", "b")
    with pytest.raises(PlaybookError):
        pb.save("!!!", "d", "b")  # slugs to empty


def test_oversized_body_rejected(tmp_path):
    pb = Playbooks(root=tmp_path)
    with pytest.raises(PlaybookError):
        pb.save("big", "d", "x" * 100_001)


def test_name_cannot_corrupt_frontmatter(tmp_path):
    pb = Playbooks(root=tmp_path)
    pb.save("weird\nname: injected", "desc", "body")
    doc = pb.read("weird-name-injected")
    assert "\n" not in doc["name"]  # newline stripped → frontmatter stays parseable
    assert doc["description"] == "desc" and doc["body"] == "body"


def test_delete(tmp_path):
    pb = Playbooks(root=tmp_path)
    pb.save("temp", "d", "b")
    assert pb.list()
    pb.delete("temp")
    assert pb.list() == []


def test_register_and_unregister_tools(tmp_path):
    client = LocalMCPClient()
    register_playbooks(client, Playbooks(root=tmp_path))
    assert {"list_playbooks", "open_playbook", "save_playbook"} <= {t.name for t in client.list_tools()}
    unregister_playbooks(client)
    assert not ({"list_playbooks", "open_playbook", "save_playbook"} & {t.name for t in client.list_tools()})


def test_tools_callable_through_mcp(tmp_path):
    client = LocalMCPClient()
    register_playbooks(client, Playbooks(root=tmp_path))
    saved = client.call_tool("save_playbook", {"name": "Refund Flow", "description": "how to refund", "body": "step 1"})
    assert saved["ok"] and saved["result"]["slug"] == "refund-flow"
    listed = client.call_tool("list_playbooks", {})
    assert listed["ok"] and any(p["name"] == "Refund Flow" for p in listed["result"])
    opened = client.call_tool("open_playbook", {"name": "refund-flow"})
    assert opened["ok"] and opened["result"]["body"] == "step 1"
