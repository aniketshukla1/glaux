"""MCP (Model Context Protocol) tool integration.

Agents call external tools the same way they call skills — through an
:class:`MCPClient`. Three implementations share that one interface:

- :class:`LocalMCPClient` — in-process tools (no external server). Used for the
  built-in demo tools.
- :class:`StdioMCPClient` — a real MCP server run as a subprocess, spoken to via
  newline-delimited JSON-RPC 2.0 over stdio (the transport used by the vast
  majority of local MCP servers, e.g. filesystem/git/fetch launched with
  ``npx``/``uvx``).
- :class:`HTTPMCPClient` — a remote MCP server over Streamable HTTP (JSON or SSE
  responses, session-id aware).

:class:`MCPRegistry` aggregates the built-in tools with any number of connected
servers behind the same ``list_tools`` / ``call_tool`` surface, and persists the
server configuration so connections survive restarts.

Every tool invocation is signed onto the ledger as an `MCP_TOOL` action.
"""

from __future__ import annotations

import ast
import json
import operator
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol


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


# --- real MCP servers (JSON-RPC 2.0) -------------------------------------

PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "athena", "version": "0.1.0"}


class _RpcError(Exception):
    """A JSON-RPC error or transport failure talking to an MCP server."""


@dataclass
class MCPServerConfig:
    """How to reach one MCP server. ``stdio`` spawns a command; ``http`` POSTs."""

    name: str
    transport: str = "stdio"  # stdio | http
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    env: dict = field(default_factory=dict)
    url: Optional[str] = None
    headers: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": list(self.args or []),
            "env": dict(self.env or {}),
            "url": self.url,
            "headers": dict(self.headers or {}),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MCPServerConfig":
        return cls(
            name=d["name"],
            transport=d.get("transport", "stdio"),
            command=d.get("command"),
            args=list(d.get("args") or []),
            env=dict(d.get("env") or {}),
            url=d.get("url"),
            headers=dict(d.get("headers") or {}),
        )


def _tool_result_to_obs(result: dict) -> dict:
    """Collapse an MCP ``tools/call`` result into the {ok, result|error} shape
    the rest of Athena uses (matching :class:`LocalMCPClient`)."""
    is_error = bool(result.get("isError"))
    structured = result.get("structuredContent")
    texts: list[str] = []
    for item in result.get("content") or []:
        if isinstance(item, dict):
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
            else:
                texts.append(json.dumps(item))
    text = "\n".join(t for t in texts if t)
    if is_error:
        return {"ok": False, "error": text or "tool reported an error"}
    payload: Any = structured if structured is not None else (text if text else result.get("content"))
    return {"ok": True, "result": payload}


class StdioMCPClient:
    """An MCP server run as a subprocess, spoken to over newline-delimited
    JSON-RPC 2.0 on stdio. Thread-safe: requests are serialized under a lock and
    responses are matched by id via a background reader thread."""

    def __init__(self, config: MCPServerConfig, timeout: float = 30.0) -> None:
        self.config = config
        self.server_name = config.name
        self.timeout = timeout
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._queue: "queue.Queue" = queue.Queue()
        self._lock = threading.Lock()
        self._id = 0
        self._tools: list[MCPTool] = []
        self.status = "new"
        self.error: Optional[str] = None

    # -- lifecycle --
    def connect(self) -> None:
        with self._lock:
            try:
                self._spawn()
                self._initialize()
                self._tools = self._fetch_tools()
                self.status = "connected"
                self.error = None
            except Exception as e:  # noqa: BLE001 - surface as status
                self.status = "error"
                self.error = f"{type(e).__name__}: {e}"
                self._kill()
                raise

    def close(self) -> None:
        with self._lock:
            self._kill()
            if self.status != "error":
                self.status = "closed"

    def _spawn(self) -> None:
        if not self.config.command:
            raise _RpcError("stdio server requires a command")
        env = dict(os.environ)
        env.update(self.config.env or {})
        self._proc = subprocess.Popen(
            [self.config.command, *(self.config.args or [])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._queue = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, args=(self._proc,), daemon=True)
        self._reader.start()

    def _read_loop(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                self._queue.put(line)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._queue.put(None)  # EOF sentinel

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass

    # -- rpc --
    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send(self, msg: dict) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise _RpcError("server process is not running")
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()

    def _request(self, method: str, params: Optional[dict] = None) -> dict:
        rid = self._next_id()
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _RpcError(f"timeout waiting for response to {method!r}")
            try:
                line = self._queue.get(timeout=remaining)
            except queue.Empty:
                raise _RpcError(f"timeout waiting for response to {method!r}")
            if line is None:
                raise _RpcError("server closed the connection")
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue  # log line or partial output — ignore
            if resp.get("id") != rid:
                continue  # notification or server-initiated request — ignore
            if "error" in resp:
                err = resp["error"]
                raise _RpcError(err.get("message", str(err)) if isinstance(err, dict) else str(err))
            return resp.get("result", {})

    def _notify(self, method: str, params: Optional[dict] = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def _initialize(self) -> None:
        self._request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": _CLIENT_INFO},
        )
        self._notify("notifications/initialized")

    def _fetch_tools(self) -> list[MCPTool]:
        result = self._request("tools/list")
        return [_mcp_tool(self.server_name, t) for t in result.get("tools", [])]

    # -- MCPClient interface --
    def list_tools(self) -> list[MCPTool]:
        return list(self._tools)

    def call_tool(self, name: str, args: dict) -> dict:
        if self._proc is None:
            return {"ok": False, "error": f"server {self.server_name!r} not connected ({self.error or self.status})"}
        with self._lock:
            try:
                result = self._request("tools/call", {"name": name, "arguments": args or {}})
            except _RpcError as e:
                return {"ok": False, "error": str(e)}
        return _tool_result_to_obs(result)


class HTTPMCPClient:
    """A remote MCP server over Streamable HTTP. POSTs JSON-RPC and handles both
    ``application/json`` and ``text/event-stream`` responses; tracks the
    ``Mcp-Session-Id`` handed back at initialize."""

    def __init__(self, config: MCPServerConfig, timeout: float = 30.0) -> None:
        self.config = config
        self.server_name = config.name
        self.timeout = timeout
        self._lock = threading.Lock()
        self._id = 0
        self._session_id: Optional[str] = None
        self._tools: list[MCPTool] = []
        self.status = "new"
        self.error: Optional[str] = None

    def connect(self) -> None:
        with self._lock:
            self._session_id = None
            try:
                self._initialize()
                self._tools = self._fetch_tools()
                self.status = "connected"
                self.error = None
            except Exception as e:  # noqa: BLE001
                self.status = "error"
                self.error = f"{type(e).__name__}: {e}"
                raise

    def close(self) -> None:
        self._session_id = None
        if self.status != "error":
            self.status = "closed"

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _post(self, payload: dict, expect_response: bool = True) -> Optional[dict]:
        import urllib.error
        import urllib.request

        if not self.config.url:
            raise _RpcError("http server requires a url")
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        headers.update(self.config.headers or {})
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        req = urllib.request.Request(
            self.config.url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            raise _RpcError(f"HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise _RpcError(f"connection error: {e.reason}")
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid
        rid = payload.get("id")
        if not expect_response:
            resp.read()
            return None
        if "text/event-stream" in (resp.headers.get("Content-Type", "")):
            return self._parse_sse(resp, rid)
        body = resp.read().decode("utf-8").strip()
        if not body:
            return None
        return self._unwrap(json.loads(body), rid)

    def _parse_sse(self, resp, rid) -> dict:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            try:
                msg = json.loads(line[len("data:"):].strip())
            except json.JSONDecodeError:
                continue
            if msg.get("id") == rid:
                return self._unwrap(msg, rid)
        raise _RpcError("no matching response in event stream")

    def _unwrap(self, msg: dict, rid) -> dict:
        if "error" in msg:
            err = msg["error"]
            raise _RpcError(err.get("message", str(err)) if isinstance(err, dict) else str(err))
        return msg.get("result", {})

    def _request(self, method: str, params: Optional[dict] = None) -> dict:
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            payload["params"] = params
        return self._post(payload, expect_response=True) or {}

    def _notify(self, method: str, params: Optional[dict] = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._post(payload, expect_response=False)

    def _initialize(self) -> None:
        self._request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": _CLIENT_INFO},
        )
        self._notify("notifications/initialized")

    def _fetch_tools(self) -> list[MCPTool]:
        result = self._request("tools/list")
        return [_mcp_tool(self.server_name, t) for t in result.get("tools", [])]

    def list_tools(self) -> list[MCPTool]:
        return list(self._tools)

    def call_tool(self, name: str, args: dict) -> dict:
        with self._lock:
            try:
                result = self._request("tools/call", {"name": name, "arguments": args or {}})
            except _RpcError as e:
                return {"ok": False, "error": str(e)}
        return _tool_result_to_obs(result)


def _mcp_tool(server: str, t: dict) -> MCPTool:
    return MCPTool(
        server=server,
        name=t.get("name", ""),
        description=t.get("description", "") or "",
        input_schema=t.get("inputSchema") or t.get("input_schema") or {},
    )


def make_client(config: MCPServerConfig):
    """Build the right transport client for a server config."""
    if config.transport == "stdio":
        return StdioMCPClient(config)
    if config.transport == "http":
        return HTTPMCPClient(config)
    raise ValueError(f"unknown MCP transport {config.transport!r} (expected 'stdio' or 'http')")


class MCPRegistry:
    """Aggregates the built-in tools with any number of connected MCP servers
    behind one :class:`MCPClient` surface, and persists server configs to disk."""

    def __init__(
        self,
        builtin: Optional[LocalMCPClient] = None,
        config_path: Optional[Path] = None,
        extra_builtins: Optional[list] = None,
    ) -> None:
        self.builtin = builtin if builtin is not None else default_local_client()
        # Always-on in-process providers beyond the demo tools (e.g. the web
        # browser). They participate in list_tools/call_tool but aren't persisted
        # like external servers.
        self.builtins: list = [self.builtin, *(extra_builtins or [])]
        self.servers: dict[str, Any] = {}
        self.configs: dict[str, MCPServerConfig] = {}
        self.config_path = Path(config_path) if config_path else None

    def _clients(self) -> list:
        return [*self.builtins, *self.servers.values()]

    # -- MCPClient interface --
    def list_tools(self) -> list[MCPTool]:
        out: list[MCPTool] = []
        for c in self._clients():
            out.extend(c.list_tools())
        return out

    def call_tool(self, name: str, args: dict) -> dict:
        for c in self._clients():
            if any(t.name == name for t in c.list_tools()):
                return c.call_tool(name, args or {})
        available = [t.name for t in self.list_tools()]
        return {"ok": False, "error": f"unknown tool {name!r}. Available tools: {available}"}

    # -- server management --
    def add_server(self, config: MCPServerConfig, connect: bool = True, persist: bool = True) -> Optional[dict]:
        if config.name in self.servers:
            self.remove_server(config.name, persist=False)
        client = make_client(config)
        self.configs[config.name] = config
        self.servers[config.name] = client
        if connect:
            try:
                client.connect()
            except Exception:  # noqa: BLE001 - status carries the error
                pass
        if persist:
            self.save()
        return self.server_status(config.name)

    def remove_server(self, name: str, persist: bool = True) -> None:
        client = self.servers.pop(name, None)
        self.configs.pop(name, None)
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
        if persist:
            self.save()

    def reconnect(self, name: str) -> dict:
        client = self.servers.get(name)
        if client is None:
            raise KeyError(name)
        try:
            client.close()
            client.connect()
        except Exception:  # noqa: BLE001
            pass
        return self.server_status(name)

    def server_status(self, name: str) -> Optional[dict]:
        client = self.servers.get(name)
        cfg = self.configs.get(name)
        if client is None or cfg is None:
            return None
        tools = client.list_tools()
        return {
            "name": name,
            "transport": cfg.transport,
            "status": getattr(client, "status", "unknown"),
            "error": getattr(client, "error", None),
            "tool_count": len(tools),
            "tools": [t.name for t in tools],
            "command": cfg.command,
            "args": list(cfg.args or []),
            "url": cfg.url,
        }

    def statuses(self) -> list[dict]:
        return [s for s in (self.server_status(n) for n in self.servers) if s is not None]

    def close_all(self) -> None:
        for c in self.servers.values():
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass

    # -- persistence --
    def save(self) -> None:
        if not self.config_path:
            return
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps([c.to_dict() for c in self.configs.values()], indent=2))

    def load(self, connect: bool = True) -> None:
        if not self.config_path or not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        for d in data:
            try:
                self.add_server(MCPServerConfig.from_dict(d), connect=connect, persist=False)
            except Exception:  # noqa: BLE001
                continue
