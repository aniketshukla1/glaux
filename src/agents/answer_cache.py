"""Semantic answer cache: a near-duplicate directive returns the prior answer.

The single biggest inference-cost lever on repeated work — a cache hit returns in
sub-millisecond with zero LLM calls, instead of a full multi-agent run. It reuses
Athena's local feature-hashing embedder (``tier_router._embed`` / ``_cosine``), so a
lookup is itself model-free, and every hit is signed to the ledger — a cached answer
is as auditable as a fresh one.

Safety: the threshold is strict (near-identical directives only, so a false hit can't
return the wrong answer), and time-sensitive directives ("latest", "current price",
"today's…") are never cached or served, so freshness-critical asks always run live.
Tunable via ``ATHENA_ANSWER_CACHE`` / ``ATHENA_CACHE_THRESHOLD`` / ``ATHENA_CACHE_MAX``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from .tier_router import _cosine, _embed

_VOLATILE = (
    "latest", "current", "right now", "today", "tonight", "this week", "this month",
    "this year", "price", "stock", "weather", "news", "recent", "as of", "up to date",
    "breaking", "live ",
)


def _athena_home() -> Path:
    return Path(os.environ.get("ATHENA_HOME", Path.home() / ".athena"))


def _is_volatile(directive: str) -> bool:
    d = (directive or "").lower()
    return any(w in d for w in _VOLATILE)


class AnswerCache:
    def __init__(self, path=None, *, threshold: float = 0.92, max_entries: int = 500, enabled: bool = True) -> None:
        self.path = Path(path or (_athena_home() / "answer_cache.jsonl"))
        self.threshold = float(threshold)
        self.max_entries = int(max_entries)
        self.enabled = bool(enabled)
        self.hits = 0
        self.misses = 0
        self._entries: list[dict] = []  # {directive, answer, model, ts, vec}
        self._load()

    @classmethod
    def from_env(cls) -> "AnswerCache":
        def _num(name, default, cast):
            try:
                return cast(os.environ.get(name, default))
            except (TypeError, ValueError):
                return cast(default)

        # Opt-in: a semantic cache can't see conversation context, so correctness wins
        # by default. Enable per workload via ATHENA_ANSWER_CACHE=1, the /api/cache
        # toggle, or `athena cache on`.
        enabled = os.environ.get("ATHENA_ANSWER_CACHE", "0").lower() in ("1", "true", "yes", "on")
        return cls(
            threshold=_num("ATHENA_CACHE_THRESHOLD", 0.92, float),
            max_entries=_num("ATHENA_CACHE_MAX", 500, int),
            enabled=enabled,
        )

    # --- persistence -----------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text().splitlines()[-self.max_entries:]:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("directive") and d.get("answer"):
                d["vec"] = _embed(d["directive"])
                self._entries.append(d)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(
            json.dumps({k: e.get(k) for k in ("directive", "answer", "model", "ts")}) + "\n"
            for e in self._entries
        ))
        os.replace(tmp, self.path)

    # --- lookup / store --------------------------------------------------

    def lookup(self, directive: str) -> Optional[dict]:
        """Return the best cached entry for a near-identical, non-volatile directive."""
        if not self.enabled or not (directive or "").strip() or _is_volatile(directive):
            return None
        q = _embed(directive)
        if not q:
            return None
        best, best_sim = None, self.threshold
        for e in self._entries:
            sim = _cosine(q, e["vec"])
            if sim >= best_sim:
                best_sim, best = sim, e
        if best is None:
            self.misses += 1
            return None
        self.hits += 1
        return {"answer": best["answer"], "directive": best["directive"], "model": best.get("model"), "similarity": best_sim}

    def store(self, directive: str, answer: str, model: Optional[str] = None) -> bool:
        if not self.enabled or _is_volatile(directive):
            return False
        if not (directive or "").strip() or not (answer or "").strip():
            return False
        q = _embed(directive)
        if not q:
            return False
        for e in self._entries:  # refresh a near-identical entry instead of duplicating
            if _cosine(q, e["vec"]) >= 0.995:
                e.update(answer=answer, model=model, ts=time.time(), vec=q)
                self._save()
                return True
        self._entries.append({"directive": directive[:500], "answer": answer, "model": model, "ts": time.time(), "vec": q})
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]
        self._save()
        return True

    def clear(self) -> int:
        n = len(self._entries)
        self._entries = []
        self.path.unlink(missing_ok=True)
        return n

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "entries": len(self._entries),
            "hits": self.hits,
            "misses": self.misses,
            "threshold": self.threshold,
        }
