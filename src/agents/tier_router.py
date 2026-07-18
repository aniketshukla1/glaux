"""Tier routing: decide fast / medium / full for a directive.

Substring keyword rules are brittle — "what is a hash **function**?" trips a
"function" build-keyword even though it's a plain question. This classifies by
*overall similarity* to labelled example directives instead: a local, dependency-
free feature-hashing bag-of-words embedding (word tokens + bigrams, stopwords
dropped, L2-normalised) scored by nearest exemplar per tier. It's deterministic
and ~sub-millisecond — no model, no network, no LLM call. When the embedding
decision is low-confidence, it falls back to the conservative keyword heuristics.

- fast   → a plainly simple question, answerable in one shot (tool-free responder)
- medium → a non-trivial single-focus task (one capable tool-using agent)
- full   → a multi-phase / multi-specialist ask (the planned + reflected swarm)
"""

from __future__ import annotations

import re
import zlib
from contextlib import contextmanager

# --- keyword fallback (conservative; used when the embedding is unsure) -------

_COMPLEX_SIGNALS = (
    "build", "implement", "create", "develop", "program ", "refactor", "debug",
    "fix ", "design", "architect", "deploy", "benchmark", "compare", "analy",
    "evaluate", "research", "investigate", "audit", "roadmap", "strategy",
    "outline", "step by step", "step-by-step", "and then", "write code",
    "write a script", "write a function", "write a program",
)

_TEAM_SIGNALS = (
    "and then", "step by step", "step-by-step", "after that", "followed by",
    "first,", "finally,", "phase", "pipeline",
)


def looks_simple(directive: str) -> bool:
    d = (directive or "").strip()
    if not d or len(d) > 240 or "\n" in d:
        return False
    low = d.lower()
    return not any(sig in low for sig in _COMPLEX_SIGNALS)


def needs_team(directive: str) -> bool:
    d = (directive or "").strip()
    low = d.lower()
    if "\n" in d or len(d) > 320:
        return True
    if any(s in low for s in _TEAM_SIGNALS):
        return True
    build = any(w in low for w in ("build", "implement", "create", "develop", "write code", "program "))
    verify = any(w in low for w in ("test", "verify", "benchmark", "unit test"))
    gather = any(w in low for w in ("research", "investigate", "gather", "analyze", "compare"))
    produce = any(w in low for w in ("report", "summariz", "write up", "write-up", "document", "recommend"))
    if (build and verify) or (gather and produce):
        return True
    return len([s for s in re.split(r"[.!?]+", d) if s.strip()]) >= 3


def _keyword_tier(directive: str) -> str:
    if looks_simple(directive):
        return "fast"
    if needs_team(directive):
        return "full"
    return "medium"


# --- embedding classifier -----------------------------------------------------

_DIM = 2048
_STOP = frozenset(
    "a an the of to in on for is are was were be been being this that these those it its "
    "as at by with from or and please can you i me my we our do does help".split()
)

# Labelled example directives per tier. Extend freely — no code change needed.
_EXEMPLARS: dict[str, list[str]] = {
    "fast": [
        "what is a bloom filter?",
        "what is a pure function in programming?",
        "who wrote war and peace?",
        "what's the capital of japan?",
        "explain recursion in one sentence",
        "define entropy in thermodynamics",
        "how far is the moon from earth?",
        "what year did the berlin wall fall?",
        "is a tomato a fruit or a vegetable?",
        "what does http stand for?",
        "who painted starry night?",
        "what is the boiling point of water?",
        "translate good morning into spanish",
        "how many bones are in the human body?",
        "what is the difference between tcp and udp?",
    ],
    "medium": [
        "refactor this function to be more readable",
        "analyze the time complexity of quicksort",
        "write a regex that matches phone numbers",
        "summarize this article in three bullet points",
        "convert this csv to json",
        "explain the tradeoffs between sql and nosql databases",
        "review this snippet for security bugs",
        "write a python function to flatten a nested list",
        "why is this query slow and how do i fix it?",
        "compute the median of these numbers",
        "draft a polite reply declining this invitation",
        "format these results as a markdown table",
        "optimize this loop for performance",
        "explain what this stack trace means",
        "generate sample data for a users table",
        "compute the crc32 checksum of a string",
        "calculate the sha256 hash of some text",
        "convert a number into roman numerals",
        "compute the nth fibonacci number",
        "calculate the exact factorial of a number",
        "validate this credit card number with the luhn algorithm",
        "write a tool to parse and evaluate this expression",
    ],
    "full": [
        "research the top vector databases and write a comparison report",
        "build a rest api for a todo app and write tests for it",
        "design a chat system architecture then implement the backend",
        "investigate the production outage find the root cause and propose fixes",
        "gather the requirements design the schema and build the crud endpoints",
        "analyze the sales data and produce an executive summary with charts",
        "scrape the reviews run sentiment analysis and visualize the trends",
        "plan the migration implement it step by step and verify each stage",
        "compare three frameworks benchmark them and recommend one with data",
        "write a spec build the feature and add integration tests",
    ],
}

_EMB_CACHE: dict | None = None


def _bucket(token: str) -> int:
    return zlib.crc32(token.encode("utf-8")) % _DIM


def _embed(text: str) -> dict[int, float]:
    """Sparse, L2-normalised feature-hashing bag of word unigrams + bigrams."""
    words = [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOP]
    grams = list(words)
    grams += [f"{words[i]}_{words[i + 1]}" for i in range(len(words) - 1)]
    vec: dict[int, float] = {}
    for g in grams:
        b = _bucket(g)
        vec[b] = vec.get(b, 0.0) + 1.0
    norm = sum(v * v for v in vec.values()) ** 0.5
    if norm == 0.0:
        return {}
    return {k: v / norm for k, v in vec.items()}


def _cosine(a: dict[int, float], b: dict[int, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(k, 0.0) for k, w in a.items())  # both are unit vectors


def _exemplar_embeddings() -> dict:
    global _EMB_CACHE
    if _EMB_CACHE is None:
        _EMB_CACHE = {tier: [_embed(x) for x in xs] for tier, xs in _EXEMPLARS.items()}
    return _EMB_CACHE


# --- learned exemplars (the self-evolving harness writes these) ---------------
#
# The Evolver appends directives it has learned belong to a given tier (from
# mis-tiered episode outcomes). They score alongside the built-in exemplars, so
# the router's decisions improve over time without any code change. Every update
# is gated + ledger-signed by the Evolver (see agents/evolution.py).

_LEARNED: dict[str, list[str]] = {}
_LEARNED_EMB: dict | None = None


def set_learned_exemplars(mapping: dict) -> None:
    """Replace the learned exemplars and invalidate their embedding cache."""
    global _LEARNED, _LEARNED_EMB
    _LEARNED = {tier: list(mapping.get(tier, [])) for tier in _EXEMPLARS}
    _LEARNED_EMB = None


def _learned_embeddings() -> dict:
    global _LEARNED_EMB
    if _LEARNED_EMB is None:
        _LEARNED_EMB = {tier: [_embed(x) for x in xs] for tier, xs in _LEARNED.items()}
    return _LEARNED_EMB


@contextmanager
def using_learned(mapping: dict):
    """Temporarily route with `mapping` as the learned set (for evaluating a
    candidate mutation without committing it), then restore the previous set."""
    global _LEARNED, _LEARNED_EMB
    prev, prev_emb = _LEARNED, _LEARNED_EMB
    try:
        set_learned_exemplars(mapping)
        yield
    finally:
        _LEARNED, _LEARNED_EMB = prev, prev_emb


def _all_embeddings() -> dict:
    base, learned = _exemplar_embeddings(), _learned_embeddings()
    return {tier: base.get(tier, []) + learned.get(tier, []) for tier in _EXEMPLARS}


def classify(directive: str) -> tuple[str | None, float, float]:
    """Return (best_tier, best_score, margin_over_runner_up). best_tier is None if
    the directive has no usable tokens."""
    q = _embed(directive)
    if not q:
        return None, 0.0, 0.0
    scores = {
        tier: max((_cosine(q, v) for v in vs), default=0.0)
        for tier, vs in _all_embeddings().items()
    }
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top_tier, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    return top_tier, top, top - second


# Confidence gates: trust the embedding when it clearly resembles a tier's
# exemplars and clearly beats the runner-up; otherwise defer to keywords.
_MIN_SCORE = 0.30
_MIN_MARGIN = 0.06


def route_tier(directive: str) -> str:
    """Pick "fast" | "medium" | "full" for a directive."""
    tier, score, margin = classify(directive)
    if tier is not None and score >= _MIN_SCORE and margin >= _MIN_MARGIN:
        return tier
    return _keyword_tier(directive)
