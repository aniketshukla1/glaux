"""Cost/budget guard — the foundational invariant that bounds a task's spend.

A single :class:`BudgetTracker` is shared across every LLM caller in a task
(router, specialists, reflector). Each call charges it; the agent loop checks it
*before* each call and halts the task cleanly when a limit is hit. So a runaway
or looping task stops at a known ceiling instead of burning tokens/dollars.

Token counts come from the provider's usage when available, else a cheap
char/4 estimate (so the guard works offline with ScriptedLLM/DemoLLM too).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional

# Rough per-1M-token USD prices (input, output) — estimates for the meter.
_PRICES = {
    "claude-opus-4-8": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (0.80, 4.0),
}
_DEFAULT_PRICE = (3.0, 15.0)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class Budget:
    max_tokens: Optional[int] = None
    max_usd: Optional[float] = None
    max_llm_calls: Optional[int] = None

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Budget":
        d = d or {}
        return cls(
            max_tokens=d.get("max_tokens"),
            max_usd=d.get("max_usd"),
            max_llm_calls=d.get("max_llm_calls"),
        )


@dataclass
class BudgetTracker:
    budget: Budget = field(default_factory=Budget)
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    llm_calls: int = 0
    # Concurrent plan branches charge the same tracker; guard the running totals.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def charge(self, model_id: str, input_tokens: int, output_tokens: int) -> None:
        p_in, p_out = _PRICES.get(model_id, _DEFAULT_PRICE)
        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.llm_calls += 1
            self.usd += (input_tokens / 1e6) * p_in + (output_tokens / 1e6) * p_out

    def exceeded(self) -> Optional[str]:
        """Reason string if any limit is reached, else None."""
        b = self.budget
        if b.max_tokens is not None and self.total_tokens >= b.max_tokens:
            return f"token budget exceeded ({self.total_tokens}/{b.max_tokens})"
        if b.max_usd is not None and self.usd >= b.max_usd:
            return f"cost budget exceeded (${self.usd:.4f}/${b.max_usd:.4f})"
        if b.max_llm_calls is not None and self.llm_calls >= b.max_llm_calls:
            return f"LLM-call budget exceeded ({self.llm_calls}/{b.max_llm_calls})"
        return None

    def snapshot(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "usd": round(self.usd, 6),
            "llm_calls": self.llm_calls,
        }


def charge_for_response(tracker: Optional[BudgetTracker], resp, system, messages) -> None:
    """Charge a tracker for one LLM response (usage if present, else estimate)."""
    if tracker is None:
        return
    usage = resp.usage or {}
    in_tok = usage.get("input_tokens")
    out_tok = usage.get("output_tokens")
    if in_tok is None:
        in_tok = estimate_tokens((system or "") + "".join(m.content for m in messages))
    if out_tok is None:
        out_tok = estimate_tokens(resp.text)
    tracker.charge(resp.model_id, in_tok, out_tok)
