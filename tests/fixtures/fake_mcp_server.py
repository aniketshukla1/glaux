#!/usr/bin/env python3
"""A minimal real MCP server over stdio, for exercising StdioMCPClient in tests.

Speaks newline-delimited JSON-RPC 2.0: handles ``initialize``,
``notifications/initialized``, ``tools/list`` and ``tools/call`` for two tools
(``echo`` and ``add``).
"""

import json
import sys

TOOLS = [
    {
        "name": "echo",
        "description": "Echo back the given text",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
    },
    {
        "name": "add",
        "description": "Add two numbers",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        },
    },
]


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        mid, method = msg.get("id"), msg.get("method")
        if method == "initialize":
            send({
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake", "version": "0.1.0"},
                },
            })
        elif method == "notifications/initialized":
            pass  # notification — no response
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name, args = params.get("name"), params.get("arguments") or {}
            if name == "echo":
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": str(args.get("text", ""))}], "isError": False,
                }})
            elif name == "add":
                total = (args.get("a", 0) or 0) + (args.get("b", 0) or 0)
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": str(total)}], "isError": False,
                }})
            else:
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True,
                }})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})


if __name__ == "__main__":
    main()
