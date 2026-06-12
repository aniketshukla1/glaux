"""MCP (Model Context Protocol) tool integration.

Agents can call external tools the same way they call skills — but tools live
behind an :class:`MCPClient`. :class:`LocalMCPClient` is a real, in-process tool
provider (no external server needed) that exposes the MCP shape: each tool has a
name, description, and input schema, and is listed/called uniformly. Real stdio
or HTTP MCP servers plug in behind the same interface (via the `mcp` SDK) as a
follow-up.

Every tool invocation is signed onto the ledger as an `MCP_TOOL` action.
"""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol


@dataclass
class MCPTool:
    server: str
    name: str
    description: str
    input_schema: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "server": self.server,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class MCPClient(Protocol):
    def list_tools(self) -> list[MCPTool]: ...

    def call_tool(self, name: str, args: dict) -> dict: ...  # {ok, result|error}


class LocalMCPClient:
    """In-process MCP-style tool provider. Register Python callables as tools."""

    def __init__(self, server_name: str = "local") -> None:
        self.server_name = server_name
        self._tools: dict[str, tuple[MCPTool, Callable]] = {}

    def register(
        self,
        name: str,
        description: str,
        fn: Callable,
        input_schema: Optional[dict] = None,
    ) -> None:
        self._tools[name] = (
            MCPTool(self.server_name, name, description, input_schema or {}),
            fn,
        )

    def list_tools(self) -> list[MCPTool]:
        return [t for (t, _fn) in self._tools.values()]

    def call_tool(self, name: str, args: dict) -> dict:
        entry = self._tools.get(name)
        if entry is None:
            available = list(self._tools)
            return {"ok": False, "error": f"unknown tool {name!r}. Available tools: {available}"}
        _tool, fn = entry
        try:
            return {"ok": True, "result": fn(**(args or {}))}
        except Exception as e:  # noqa: BLE001 - surface tool errors as observations
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# --- built-in demo tools -------------------------------------------------

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("only arithmetic over numbers is allowed")


def calc(expression: str):
    """Evaluate a safe arithmetic expression (numbers and + - * / % ** only)."""
    return _safe_eval(ast.parse(str(expression), mode="eval"))


def word_count(text: str) -> int:
    return len(str(text).split())


def uppercase(text: str) -> str:
    return str(text).upper()


def default_local_client() -> LocalMCPClient:
    """A LocalMCPClient pre-loaded with a few safe demo tools."""
    client = LocalMCPClient(server_name="athena-builtin")
    client.register(
        "calc", "Evaluate a safe arithmetic expression", calc,
        {"expression": "string (e.g. '2 * (3 + 4)')"},
    )
    client.register(
        "word_count", "Count the words in a string", word_count, {"text": "string"}
    )
    client.register("uppercase", "Uppercase a string", uppercase, {"text": "string"})
    return client
