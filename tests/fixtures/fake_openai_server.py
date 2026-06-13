#!/usr/bin/env python3
"""A standalone OpenAI-compatible server, used to stand in for a real local
model runtime (llama.cpp / vLLM) when testing LocalModelManager's lifecycle.

Serves GET /v1/models (readiness probe) and POST /v1/chat/completions.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._send({"object": "list", "data": [{"id": "local", "object": "model"}]})
        else:
            self._send({"ok": True})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        last = next((m["content"] for m in reversed(body.get("messages", [])) if m["role"] == "user"), "")
        self._send({
            "choices": [{"message": {"role": "assistant", "content": f"local-echo:{last}"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        })


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    # accept (and ignore) any runtime-style flags so the same script stands in for real servers
    args, _ = ap.parse_known_args()
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
