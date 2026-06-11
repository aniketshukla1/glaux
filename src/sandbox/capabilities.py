"""Capability declarations and execution results for the skill sandbox.

A skill declares, up front, exactly what it is allowed to touch. The sandbox
enforces these at the boundary and statically (future: AST check at synthesis).
Default is deny: no network, no filesystem outside scratch, no secrets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Capabilities:
    net: bool = False
    """Allow network access. Default deny."""

    fs_read: list[str] = field(default_factory=list)
    """Absolute paths (or dirs) the skill may read, beyond its scratch dir."""

    fs_write: list[str] = field(default_factory=list)
    """Absolute paths (or dirs) the skill may write, beyond its scratch dir."""

    time_limit_s: float = 5.0
    """Wall-clock budget; the process group is killed when exceeded."""

    mem_mb: int = 256
    """Resident memory ceiling in MB; breach kills the process group."""

    secrets: list[str] = field(default_factory=list)
    """Named secrets to inject as scoped env vars. Undeclared secrets are invisible."""

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Capabilities":
        d = d or {}
        return cls(
            net=d.get("net", False),
            fs_read=list(d.get("fs_read", [])),
            fs_write=list(d.get("fs_write", [])),
            time_limit_s=d.get("time_limit_s", 5.0),
            mem_mb=d.get("mem_mb", 256),
            secrets=list(d.get("secrets", [])),
        )

    def to_job(self) -> dict:
        """The subset the in-sandbox harness needs to enforce guards."""
        return {
            "net": self.net,
            "fs_read": list(self.fs_read),
            "fs_write": list(self.fs_write),
            "time_limit_s": self.time_limit_s,
        }


@dataclass
class SandboxResult:
    ok: bool
    return_value: Any = None
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    traceback: Optional[str] = None
    killed_reason: Optional[str] = None  # "timeout" | "memory" | "halted" | None
    exit_code: Optional[int] = None
    duration_s: float = 0.0
    peak_rss_mb: float = 0.0
