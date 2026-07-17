"""Workspace: real files under a jailed, size-capped directory.

The skill sandbox is a *safe tool factory* — Python functions with no host
filesystem. This is the opposite trade-off, opt-in: an agent that needs to produce
real artifacts (a file, a small project) can, but only inside one directory it can
never escape, with per-file and total-size caps, and with every write callable
through the MCP surface so the swarm signs it to the ledger.

Enable by exposing the tools (``register_workspace``); the daemon does so only when
``ATHENA_WORKSPACE`` is set. Default location: ``<ATHENA_HOME>/workspace``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path


def _athena_home() -> Path:
    return Path(os.environ.get("ATHENA_HOME", Path.home() / ".athena"))


class WorkspaceError(Exception):
    """A jail violation or a limit breach — surfaced to the agent as a tool error."""


class Workspace:
    def __init__(
        self,
        root: str | os.PathLike | None = None,
        *,
        max_file_bytes: int = 5 * 1024 * 1024,
        max_total_bytes: int = 200 * 1024 * 1024,
    ) -> None:
        self.root = Path(root or (_athena_home() / "workspace")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes

    # --- jail ------------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        """Resolve ``path`` under the workspace root, rejecting any escape."""
        if not isinstance(path, str) or not path.strip():
            raise WorkspaceError("path is required")
        p = (self.root / path.lstrip("/")).resolve()
        if p != self.root and self.root not in p.parents:
            raise WorkspaceError(f"path {path!r} escapes the workspace")
        return p

    def _rel(self, p: Path) -> str:
        return str(p.relative_to(self.root))

    def _total_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.root.rglob("*") if f.is_file())

    # --- tools -----------------------------------------------------------

    def write_file(self, path: str, content: str = "") -> dict:
        p = self._resolve(path)
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        if len(data) > self.max_file_bytes:
            raise WorkspaceError(f"file too large ({len(data)} bytes, max {self.max_file_bytes})")
        existing = p.stat().st_size if p.exists() else 0
        if self._total_bytes() - existing + len(data) > self.max_total_bytes:
            raise WorkspaceError("workspace size limit reached")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return {"path": self._rel(p), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()[:16]}

    def read_file(self, path: str) -> str:
        p = self._resolve(path)
        if not p.is_file():
            raise WorkspaceError(f"no such file {path!r}")
        return p.read_text(errors="replace")[: self.max_file_bytes]

    def list_files(self, path: str = ".") -> list[str]:
        p = self._resolve(path)
        base = p if p.is_dir() else self.root
        return sorted(self._rel(f) for f in base.rglob("*") if f.is_file())

    def make_dir(self, path: str) -> dict:
        p = self._resolve(path)
        p.mkdir(parents=True, exist_ok=True)
        return {"path": self._rel(p), "created": True}

    def delete_path(self, path: str) -> dict:
        p = self._resolve(path)
        if p == self.root:
            raise WorkspaceError("refusing to delete the workspace root")
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
        return {"path": self._rel(p), "deleted": True}


def register_workspace(client, workspace: Workspace) -> None:
    """Expose the workspace file tools on a LocalMCPClient (so agents can call them
    via call_mcp, and every call is signed to the ledger)."""
    client.register(
        "write_file", "Create or overwrite a text file in the workspace (jailed, size-capped).",
        workspace.write_file, {"path": "string (relative)", "content": "string"},
    )
    client.register(
        "read_file", "Read a text file from the workspace.",
        workspace.read_file, {"path": "string (relative)"},
    )
    client.register(
        "list_files", "List files in the workspace (recursive).",
        workspace.list_files, {"path": "string (relative, default '.')"},
    )
    client.register(
        "make_dir", "Create a directory in the workspace.",
        workspace.make_dir, {"path": "string (relative)"},
    )
    client.register(
        "delete_path", "Delete a file or directory in the workspace.",
        workspace.delete_path, {"path": "string (relative)"},
    )
