"""Semantic answer cache: near-identical asks return the prior answer, safely."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.answer_cache import AnswerCache  # noqa: E402


def test_store_and_near_identical_hit(tmp_path):
    c = AnswerCache(path=tmp_path / "c.jsonl", threshold=0.9)
    assert c.lookup("what is a bloom filter") is None  # cold miss
    c.store("what is a bloom filter", "A probabilistic set.", model="m")
    hit = c.lookup("what is a bloom filter?")  # punctuation-only difference
    assert hit and hit["answer"] == "A probabilistic set." and hit["similarity"] >= 0.9


def test_different_directive_misses(tmp_path):
    c = AnswerCache(path=tmp_path / "c.jsonl", threshold=0.9)
    c.store("reverse the string hello", "olleh")
    assert c.lookup("reverse the string world") is None  # different argument → no false hit


def test_volatile_directives_never_cached_or_served(tmp_path):
    c = AnswerCache(path=tmp_path / "c.jsonl", threshold=0.5)
    assert c.store("what is the latest news", "stuff") is False
    c.store("what is a widget", "a thing")
    assert c.lookup("what is the current widget") is None  # 'current' short-circuits the lookup


def test_disabled_cache_is_inert(tmp_path):
    c = AnswerCache(path=tmp_path / "c.jsonl", enabled=False)
    assert c.store("something here", "y") is False
    assert c.lookup("something here") is None


def test_persistence_across_instances(tmp_path):
    p = tmp_path / "c.jsonl"
    AnswerCache(path=p).store("compute the nth fibonacci number", "use dynamic programming")
    hit = AnswerCache(path=p).lookup("compute the nth fibonacci number")
    assert hit and hit["answer"] == "use dynamic programming"


def test_refresh_replaces_instead_of_duplicating(tmp_path):
    c = AnswerCache(path=tmp_path / "c.jsonl")
    c.store("define entropy in thermodynamics", "answer one")
    c.store("define entropy in thermodynamics", "answer two")
    assert c.stats()["entries"] == 1
    assert c.lookup("define entropy in thermodynamics")["answer"] == "answer two"


def test_clear(tmp_path):
    c = AnswerCache(path=tmp_path / "c.jsonl")
    c.store("explain quicksort partitioning", "pivot then recurse")
    assert c.clear() == 1 and c.stats()["entries"] == 0
    assert c.lookup("explain quicksort partitioning") is None


def test_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ATHENA_HOME", str(tmp_path))
    monkeypatch.setenv("ATHENA_ANSWER_CACHE", "0")
    assert AnswerCache.from_env().enabled is False
    monkeypatch.setenv("ATHENA_ANSWER_CACHE", "1")
    monkeypatch.setenv("ATHENA_CACHE_THRESHOLD", "0.8")
    c = AnswerCache.from_env()
    assert c.enabled is True and c.threshold == 0.8


def test_hit_miss_counters(tmp_path):
    c = AnswerCache(path=tmp_path / "c.jsonl", threshold=0.9)
    c.store("translate good morning into spanish", "buenos días")
    c.lookup("translate good morning into spanish")  # hit
    c.lookup("an entirely unrelated question about zebras")  # miss
    s = c.stats()
    assert s["hits"] == 1 and s["misses"] == 1
