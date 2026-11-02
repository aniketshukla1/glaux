"""Phase 2: tri-partite memory, retrieval policy, and hygiene.

Uses the deterministic HashingEmbedder, so everything runs offline. Requires
the native `athenadb` module (built into the venv via maturin).
"""

from __future__ import annotations

import pytest

pytest.importorskip("athenadb")

from memory import (  # noqa: E402
    HashingEmbedder,
    MemoryHit,
    MemoryManager,
    RetrievalPolicy,
    SCHEMA_VERSION,
)
from memory.retriever import apply_policy, estimate_tokens, score_hit  # noqa: E402


# --- embedding -----------------------------------------------------------


def test_embedding_is_deterministic():
    e = HashingEmbedder()
    assert e.embed_one("hello world") == e.embed_one("hello world")
    assert e.model_id == "hashing-v1-d256"


def test_identical_text_is_self_similar():
    e = HashingEmbedder()
    v = e.embed_one("the sky is blue today")
    # cosine with itself == 1 (vectors are L2-normalized)
    assert abs(sum(a * b for a, b in zip(v, v)) - 1.0) < 1e-6


# --- basic add / search --------------------------------------------------


def test_add_and_retrieve_fact(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    mm.semantic.add_fact("Glaux uses Ed25519 for agent identity")
    hits = mm.semantic.search("what signing scheme do agents use", k=3)
    assert hits
    assert "Ed25519" in hits[0].text


def test_schema_version_stored(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    mm.semantic.add_fact("a durable fact")
    hit = mm.semantic.search("durable fact", k=1)[0]
    assert hit.metadata["schema_version"] == SCHEMA_VERSION
    assert hit.metadata["layer"] == "semantic"
    assert hit.metadata["tenant"] == "default"


def test_layers_are_namespace_isolated(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    sem_id = mm.semantic.add_fact("alpha beta gamma delta")
    mm.episodic.log("epsilon zeta eta theta")
    # querying episodic with the semantic text must not surface the semantic record
    ep_hits = mm.episodic.search("alpha beta gamma delta", k=5)
    assert sem_id not in [h.id for h in ep_hits]
    # and the semantic layer finds its own record
    sem_hits = mm.semantic.search("alpha beta gamma delta", k=5)
    assert sem_id in [h.id for h in sem_hits]


# --- dedup ---------------------------------------------------------------


def test_dedup_merges_identical_text(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    id1 = mm.semantic.add_fact("the mitochondria is the powerhouse of the cell")
    id2 = mm.semantic.add_fact("the mitochondria is the powerhouse of the cell")
    assert id1 == id2
    assert len(mm) == 1  # merged, not duplicated


def test_distinct_text_not_deduped(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    mm.semantic.add_fact("completely unrelated subject matter here")
    mm.semantic.add_fact("an entirely different topic with other words")
    assert len(mm) == 2


# --- retrieval policy (unit) --------------------------------------------


def test_recency_decay_prefers_recent():
    now = 1_000_000.0
    day = 86400.0
    policy = RetrievalPolicy(recency_half_life_days=14.0)
    recent = MemoryHit("r", 0.8, "x", {"created_at": now - day}, "ns")
    old = MemoryHit("o", 0.8, "x", {"created_at": now - 60 * day}, "ns")
    assert score_hit(recent, now, policy) > score_hit(old, now, policy)


def test_success_weight_prefers_proven_skills():
    now = 1_000_000.0
    policy = RetrievalPolicy(success_weight=2.0)
    proven = MemoryHit("p", 0.5, "x", {"success_rate": 0.9}, "ns")
    untested = MemoryHit("u", 0.5, "x", {"success_rate": 0.1}, "ns")
    assert score_hit(proven, now, policy) > score_hit(untested, now, policy)


def test_token_budget_truncates():
    now = 1_000_000.0
    policy = RetrievalPolicy(max_tokens=150)  # ~150 tokens
    big = "word " * 100  # ~500 chars => ~125 tokens
    hits = [
        MemoryHit(f"h{i}", 0.9 - i * 0.01, big, {"created_at": now}, "ns")
        for i in range(5)
    ]
    out = apply_policy("q", hits, k=5, policy=policy, now=now)
    assert len(out) == 1  # only the first fits the budget


def test_estimate_tokens():
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 40) == 10


# --- persistence ---------------------------------------------------------


def test_memory_persists_across_reopen(tmp_path):
    path = tmp_path / "db"
    mm = MemoryManager(path)
    mm.semantic.add_fact("persisted across a restart")
    mm.snapshot()
    del mm  # drop the AthenaDB handle

    reopened = MemoryManager(path)
    hits = reopened.semantic.search("persisted across a restart", k=1)
    assert hits
    assert "persisted" in hits[0].text


# --- hygiene: archive / compress ----------------------------------------


def test_archive_removes_from_live_search(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    mm.semantic.add_fact("forgettable trivia about nothing important")
    before = len(mm)
    hit = mm.semantic.search("forgettable trivia", k=1)[0]
    mm.semantic.archive(hit)
    # still in the DB (reversible), but gone from live search
    assert len(mm) == before
    live = mm.semantic.search("forgettable trivia", k=5)
    assert hit.id not in [h.id for h in live]


def test_episode_compression(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    mm.episodic.log("deploy service A and watch metrics")
    mm.episodic.log("deploy service B and watch metrics")
    mm.episodic.log("deploy service C and watch metrics")

    episodes = mm.episodic.candidates("deploy service watch metrics", 10)
    assert len(episodes) == 3

    lessons_id = mm.episodic.compress(
        episodes, summarizer=lambda texts: f"LESSON: deploys observed x{len(texts)}"
    )

    lessons = mm.episodic.search("deploys observed lesson", k=5)
    assert lessons_id in [h.id for h in lessons]
    # originals archived -> not in live episodic search
    live_ids = [h.id for h in mm.episodic.search("deploy service", k=10)]
    for ep in episodes:
        assert ep.id not in live_ids


def test_procedural_favors_higher_success_rate(tmp_path):
    mm = MemoryManager(tmp_path / "db")
    mm.procedural.add_skill(
        "sort numbers ascending", "def f(x): return sorted(x)", success_rate=0.95,
        description="reliable sort", skill_id="good",
    )
    mm.procedural.add_skill(
        "sort values ascending", "def f(x): return sorted(x)", success_rate=0.05,
        description="flaky sort", skill_id="bad",
    )
    hits = mm.procedural.search("sort ascending", k=2)
    assert hits[0].id == "good"
