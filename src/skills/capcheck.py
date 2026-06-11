"""Static capability check on synthesized skill code (AST walk).

A first line of defense at synthesis time: reject code that obviously reaches
beyond its declared capabilities (network imports without `net`, process/FFI
escape hatches, file writes without `fs_write`). The sandbox is the real
enforcement boundary at run time; this just stops bad skills from ever being
stored.
"""

from __future__ import annotations

import ast

# modules that imply a capability
_NET_MODULES = {"socket", "http", "urllib", "urllib2", "requests", "httpx", "ftplib", "smtplib", "aiohttp"}
_PROC_MODULES = {"subprocess", "multiprocessing", "ctypes", "cffi"}
_WRITE_MODES = ("w", "a", "x", "+")


def static_cap_check(code: str, caps: dict) -> list[str]:
    """Return a list of capability violations (empty == clean)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"syntax error: {e}"]

    caps = caps or {}
    net_ok = bool(caps.get("net", False))
    fs_write_ok = bool(caps.get("fs_write"))
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            roots = set()
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
            if isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
            for root in roots:
                if root in _PROC_MODULES:
                    violations.append(f"import of '{root}' (process/FFI escape) is not permitted")
                if root in _NET_MODULES and not net_ok:
                    violations.append(f"network import '{root}' requires the 'net' capability")

        # open(path, 'w'|'a'|...) without fs_write
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
        ):
            mode = None
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = kw.value.value
            if isinstance(mode, str) and any(c in mode for c in _WRITE_MODES) and not fs_write_ok:
                violations.append("file write via open() requires the 'fs_write' capability")

    return violations
