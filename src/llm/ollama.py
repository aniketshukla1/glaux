"""Ollama backend — run the swarm against a local model for real testing.

Talks to a local Ollama server's ``/api/chat`` over stdlib HTTP (no extra deps).
Same :class:`LLMClient` interface as every other backend, so it drops into the
gateway and the swarm unchanged. Token usage is read from Ollama's
``prompt_eval_count`` / ``eval_count`` so the cost meter and budget guard work.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from .gateway import LLMResponse, Message

DEFAULT_HOST = "http://localhost:11434"


def _host(host: Optional[str]) -> str:
    return host or os.environ.get("OLLAMA_HOST", DEFAULT_HOST)


def ollama_status(host: Optional[str] = None) -> dict:
    """Probe an Ollama server: is it reachable, and what models are pulled?"""
    base = _host(host)
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode())
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return {"reachable": True, "host": base, "models": models}
    except Exception as e:  # noqa: BLE001 - any failure means "not reachable"
        return {"reachable": False, "host": base, "models": [], "error": str(e)}


class OllamaClient:
    def __init__(
        self,
        model: str = "llama3.2",
        *,
        host: Optional[str] = None,
        timeout: float = 180.0,
        default_max_tokens: int = 1024,
    ) -> None:
        self.model = model
        self.model_id = f"ollama:{model}"
        self.host = _host(host)
        self.timeout = timeout
        self._default_max_tokens = default_max_tokens

    def complete(
        self,
        messages: list[Message],
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        seed: Optional[int] = None,
    ) -> LLMResponse:
        chat = []
        if system:
            chat.append({"role": "system", "content": system})
        chat.extend({"role": m.role, "content": m.content} for m in messages)

        options = {"temperature": temperature, "num_predict": max_tokens or self._default_max_tokens}
        if seed is not None:
            options["seed"] = seed
        payload = {"model": self.model, "messages": chat, "stream": False, "options": options}

        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            # Surface Ollama's own error body (e.g. a model that can't load) instead
            # of a bare "HTTP 500", so the caller can show something actionable.
            body = e.read().decode("utf-8", "replace") if e.fp else ""
            detail = body
            try:
                detail = json.loads(body).get("error", body)
            except Exception:  # noqa: BLE001 - body wasn't JSON
                pass
            raise RuntimeError(
                f"Ollama returned HTTP {e.code} for model {self.model!r}: {detail or e.reason}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Could not reach Ollama at {self.host} (model {self.model!r}): {e.reason}. "
                f"Is `ollama serve` running?"
            ) from e

        text = (data.get("message") or {}).get("content", "")
        usage = {
            "input_tokens": data.get("prompt_eval_count"),
            "output_tokens": data.get("eval_count"),
        }
        return LLMResponse(text=text, model_id=self.model_id, usage=usage, raw=data)
