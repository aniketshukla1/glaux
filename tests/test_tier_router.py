"""Embedding-based tier router: fast / medium / full classification."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.tier_router import _keyword_tier, classify, route_tier  # noqa: E402


def test_routes_the_three_tiers():
    # fast: plain questions
    assert route_tier("who wrote Hamlet?") == "fast"
    assert route_tier("what is a bloom filter?") == "fast"
    assert route_tier("what is the capital of France?") == "fast"
    # medium: single-focus tasks
    assert route_tier("analyze the time complexity of quicksort") == "medium"
    assert route_tier("refactor this helper to be readable") == "medium"
    # full: multi-phase / multi-specialist
    assert route_tier("build a REST API for todos and write tests for it") == "full"
    assert route_tier("research the top vector databases and write a comparison report") == "full"


def test_embedding_beats_brittle_keywords():
    # The substring keyword rule mis-routes these; the embedding classifier fixes them.
    d1 = "write a regex to validate an email address"
    assert _keyword_tier(d1) == "fast"     # keyword: no complex substring -> fast (wrong)
    assert route_tier(d1) == "medium"       # embedding: resembles other single-focus tasks

    d2 = "design a system for real-time chat, then implement the backend"
    assert _keyword_tier(d2) == "medium"   # keyword misses the second phase
    assert route_tier(d2) == "full"         # embedding: clearly multi-phase


def test_hash_function_question_is_fast_not_a_build_task():
    # the classic false-positive: "function" must not make a plain question look like work
    assert route_tier("in one sentence, what is a hash function?") == "fast"


def test_confidence_and_edge_inputs():
    tier, score, margin = classify("build a rest api for todos and write tests for it")
    assert tier == "full" and score > 0.3 and margin > 0.06
    # never crashes on degenerate input; always returns a valid tier
    for d in ("", "   ", "!!!", "asdfqwer"):
        assert route_tier(d) in ("fast", "medium", "full")
