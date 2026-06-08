"""Retrieval policy — the part that makes the brain smart.

Storing memories is easy; *choosing what to put in the context window* is the
hard part. A :class:`RetrievalPolicy` rescales raw cosine similarity by recency
and/or success, optionally reranks, then packs results into a token budget so
the reasoning window never overflows.

Per-layer defaults (set by each layer):
- semantic   → similarity only
- episodic   → recency-decayed
- procedural → success-rate-weighted
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Protocol

from .record import MemoryHit


def estimate_tokens(text: str) -> int:
    """Cheap, tokenizer-free estimate (~4 chars/token)."""
    return max(1, len(text) // 4)


@dataclass
class RetrievalPolicy:
    recency_half_life_days: Optional[float] = None
    """If set, score *= exp(-age_days / half_life)."""

    success_weight: float = 0.0
    """If > 0, score *= (1 + success_weight * success_rate)."""

    max_tokens: int = 2000
    """Greedy token budget for the returned set."""

    candidate_multiplier: int = 5
    """Fetch k * this many candidates before re-ranking."""

    rerank: bool = False
    """Apply the optional cross-encoder reranker before budgeting."""


class Reranker(Protocol):
    def rerank(self, query: str, hits: list[MemoryHit]) -> list[MemoryHit]: ...


class IdentityReranker:
    """Passthrough. Real cross-encoder reranking is a future, optional backend."""

    def rerank(self, query: str, hits: list[MemoryHit]) -> list[MemoryHit]:
        return hits


def score_hit(hit: MemoryHit, now: float, policy: RetrievalPolicy) -> float:
    score = hit.similarity
    if policy.recency_half_life_days:
        created = float(hit.metadata.get("created_at", now))
        age_days = max(0.0, (now - created) / 86400.0)
        score *= math.exp(-age_days / policy.recency_half_life_days)
    if policy.success_weight:
        success_rate = float(hit.metadata.get("success_rate", 0.0) or 0.0)
        score *= 1.0 + policy.success_weight * success_rate
    return score


def apply_policy(
    query: str,
    hits: list[MemoryHit],
    k: int,
    policy: RetrievalPolicy,
    now: float,
    reranker: Optional[Reranker] = None,
) -> list[MemoryHit]:
    for h in hits:
        h.score = score_hit(h, now, policy)
    ranked = sorted(hits, key=lambda h: h.score, reverse=True)

    if policy.rerank and reranker is not None:
        ranked = reranker.rerank(query, ranked)

    out: list[MemoryHit] = []
    used = 0
    for h in ranked:
        if len(out) >= k:
            break
        cost = estimate_tokens(h.text)
        if out and used + cost > policy.max_tokens:
            break
        used += cost
        out.append(h)
    return out
