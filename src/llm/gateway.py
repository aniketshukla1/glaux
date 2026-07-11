"""LLM gateway seam.

All model calls go through the :class:`LLMClient` interface so the backend is
swappable and so the agent runtime is testable offline. The default
:class:`ScriptedLLM` returns canned/handler-driven responses with no network —
the whole ReAct loop runs deterministically in tests. :class:`AnthropicClient`
is the real backend (lazy-imported; never touched by tests).

This is the single place model access lives; multi-model routing, fallback, and
cost-based selection slot in here later without touching agents.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    text: str
    model_id: str
    usage: dict = field(default_factory=dict)
    raw: Any = None


class LLMClient(Protocol):
    model_id: str

    def complete(
        self,
        messages: list[Message],
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        seed: Optional[int] = None,
    ) -> LLMResponse: ...


def stream_complete(client, messages, *, on_delta: Optional[Callable[[str], None]] = None, **kw) -> LLMResponse:
    """Stream a completion when the client supports it (calling ``on_delta(text)``
    per chunk), otherwise fall back to a single ``complete()`` and emit the whole
    text once. Always returns the full :class:`LLMResponse`."""
    streamer = getattr(client, "stream", None)
    if on_delta is not None and callable(streamer):
        return streamer(messages, on_delta=on_delta, **kw)
    resp = client.complete(messages, **kw)
    if on_delta is not None and resp.text:
        on_delta(resp.text)
    return resp


class ScriptedLLM:
    """Deterministic, offline LLM for tests.

    Provide either ``responses`` (returned in order) or a ``handler`` callable
    ``(messages, system) -> str``. Records every call for assertions.
    """

    model_id = "scripted-v1"

    def __init__(
        self,
        responses: Optional[list[str]] = None,
        handler: Optional[Callable[[list[Message], Optional[str]], str]] = None,
    ) -> None:
        self._responses = list(responses or [])
        self._handler = handler
        self.calls: list[dict] = []

    def complete(
        self,
        messages: list[Message],
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        seed: Optional[int] = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "system": system})
        if self._handler is not None:
            text = self._handler(messages, system)
        elif self._responses:
            text = self._responses.pop(0)
        else:
            text = '```json\n{"action": "finish", "result": "no script", "success": false}\n```'
        return LLMResponse(text=text, model_id=self.model_id, usage={}, raw=None)


class AnthropicClient:
    """Real backend over the Anthropic SDK (lazy-imported).

    Uses prompt caching on the system prompt. ``seed`` is accepted for a uniform
    interface but ignored by the API (the reproducibility envelope still records
    it). Not exercised by the test suite.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        *,
        api_key: Optional[str] = None,
        default_max_tokens: int = 1024,
    ) -> None:
        import anthropic  # lazy: module imports without the SDK installed

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        self.model_id = model
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
        kwargs: dict = {
            "model": self.model_id,
            "max_tokens": max_tokens or self._default_max_tokens,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            # Cache the (stable) system prompt across calls. Default is Anthropic's
            # 5-minute ephemeral cache; ATHENA_ANTHROPIC_CACHE_TTL=1h opts into the
            # extended 1-hour cache (keeps the prefix warm across sparse sessions).
            cache_control: dict = {"type": "ephemeral"}
            ttl = os.environ.get("ATHENA_ANTHROPIC_CACHE_TTL", "").strip().lower()
            if ttl in ("1h", "1hr", "3600s"):
                cache_control["ttl"] = "1h"
                kwargs["extra_headers"] = {"anthropic-beta": "extended-cache-ttl-2025-04-11"}
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": cache_control}]
        msg = self._client.messages.create(**kwargs)
        text = "".join(block.text for block in msg.content if block.type == "text")
        usage = {
            "input_tokens": getattr(msg.usage, "input_tokens", None),
            "output_tokens": getattr(msg.usage, "output_tokens", None),
        }
        return LLMResponse(text=text, model_id=self.model_id, usage=usage, raw=msg)
