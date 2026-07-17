"""Jailed, size-capped workspace file tools."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.mcp import LocalMCPClient  # noqa: E402
from agents.workspace import (  # noqa: E402
    Workspace,
    WorkspaceError,
    register_workspace,
    unregister_workspace,
)


def test_write_read_list(tmp_path):
    ws = Workspace(root=tmp_path)
    r = ws.write_file("hello.txt", "hi there")
    assert r["bytes"] == 8 and r["path"] == "hello.txt" and r["sha256"]
    assert ws.read_file("hello.txt") == "hi there"
    ws.write_file("sub/dir/note.md", "# note")
    assert set(ws.list_files()) == {"hello.txt", "sub/dir/note.md"}


def test_traversal_escape_is_blocked(tmp_path):
    ws = Workspace(root=tmp_path)
    for bad in ("../evil.txt", "sub/../../evil", "a/../../../b"):
        with pytest.raises(WorkspaceError):
            ws.write_file(bad, "x")


def test_absolute_path_is_jailed_not_escaped(tmp_path):
    ws = Workspace(root=tmp_path)
    # a leading slash is treated as workspace-relative, never the real /etc
    ws.write_file("/etc/passwd", "not the real one")
    assert (Path(tmp_path) / "etc" / "passwd").is_file()
    assert Path("/etc/passwd").read_text() != "not the real one"


def test_file_and_total_size_caps(tmp_path):
    ws = Workspace(root=tmp_path, max_file_bytes=10, max_total_bytes=15)
    with pytest.raises(WorkspaceError):
        ws.write_file("big.txt", "x" * 11)  # over per-file cap
    ws.write_file("a.txt", "x" * 10)
    with pytest.raises(WorkspaceError):
        ws.write_file("b.txt", "y" * 10)  # would blow the total cap


def test_delete_and_root_protection(tmp_path):
    ws = Workspace(root=tmp_path)
    ws.write_file("x.txt", "hi")
    ws.delete_path("x.txt")
    assert ws.list_files() == []
    with pytest.raises(WorkspaceError):
        ws.delete_path(".")  # never delete the root


def test_register_and_unregister_tools(tmp_path):
    client = LocalMCPClient()
    assert "write_file" not in {t.name for t in client.list_tools()}
    register_workspace(client, Workspace(root=tmp_path))
    assert {"write_file", "read_file", "list_files", "make_dir", "delete_path"} <= {
        t.name for t in client.list_tools()
    }
    unregister_workspace(client)
    assert "write_file" not in {t.name for t in client.list_tools()}
