"""Self-evolving harness: the router learns from mis-tiered episodes, gated."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents import tier_router  # noqa: E402
from agents.evolution import Episode, Evolver  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_learned():
    tier_router.set_learned_exemplars({})  # isolate the module-global learned set
    yield
    tier_router.set_learned_exemplars({})


def test_ideal_tier_rules():
    assert Episode("x", "fast", success=False).ideal_tier() == "medium"      # under-powered
    assert Episode("x", "medium", success=False).ideal_tier() == "full"      # under-powered
    assert Episode("x", "full", success=False).ideal_tier() == "full"        # can't bump past top
    assert Episode("x", "medium", success=True, escalated=True).ideal_tier() == "full"
    assert Episode("x", "full", success=True, n_roles=1).ideal_tier() == "medium"  # over-powered
    assert Episode("x", "full", success=True, n_roles=3).ideal_tier() == "full"    # justified
    assert Episode("x", "fast", success=True).ideal_tier() == "fast"         # correct as-is


def test_record_and_read_roundtrip(tmp_path):
    ev = Evolver(root=tmp_path)
    ev.record("do a thing", "medium", success=True, score=0.9, n_roles=1)
    eps = ev.episodes()
    assert len(eps) == 1 and eps[0].tier == "medium" and eps[0].success is True


def test_evolve_learns_a_mistier_and_improves_routing(tmp_path):
    ev = Evolver(root=tmp_path)
    d = "what is a florb?"
    t0 = tier_router.route_tier(d)          # what the base router does today
    ev.record(d, t0, success=False)         # it failed → was under-powered
    ideal = ev.episodes()[0].ideal_tier()
    assert ideal != t0                      # a genuine mis-tier to learn from

    rep = ev.evolve()
    assert rep["applied"] is True
    assert rep["accuracy"] > rep["baseline_accuracy"]
    assert tier_router.route_tier(d) == ideal   # the harness now routes it correctly


def test_gate_rejects_when_nothing_new(tmp_path):
    ev = Evolver(root=tmp_path)
    d = "what is a florb?"
    t0 = tier_router.route_tier(d)
    ev.record(d, t0, success=True)          # correctly tiered → ideal == used
    rep = ev.evolve()
    assert rep["applied"] is False and "nothing new" in rep["reason"]


def test_evolve_with_no_episodes_is_a_noop(tmp_path):
    ev = Evolver(root=tmp_path)
    rep = ev.evolve()
    assert rep["applied"] is False and "no episodes" in rep["reason"]


def test_revert_rolls_back_learned_routing(tmp_path):
    ev = Evolver(root=tmp_path)
    d = "what is a florb?"
    t0 = tier_router.route_tier(d)
    ev.record(d, t0, success=False)
    ideal = ev.episodes()[0].ideal_tier()
    ev.evolve()
    assert tier_router.route_tier(d) == ideal
    out = ev.revert()
    assert out["reverted"] is True
    assert tier_router.route_tier(d) == t0   # back to the original routing
    assert ev.status()["can_revert"] is False


def test_learned_exemplars_persist_across_instances(tmp_path):
    d = "what is a florb?"
    ev = Evolver(root=tmp_path)
    t0 = tier_router.route_tier(d)
    ev.record(d, t0, success=False)
    ideal = ev.episodes()[0].ideal_tier()
    ev.evolve()
    # a fresh Evolver over the same dir reloads learned exemplars + applies them
    tier_router.set_learned_exemplars({})
    Evolver(root=tmp_path)
    assert tier_router.route_tier(d) == ideal


def test_evolution_is_signed_to_the_ledger(tmp_path):
    pytest.importorskip("athena_ledger")
    from core.ledger import Ledger
    from identity import AgentIdentity

    led = Ledger()
    ev = Evolver(root=tmp_path)
    d = "what is a florb?"
    t0 = tier_router.route_tier(d)
    ev.record(d, t0, success=False)
    rep = ev.evolve(ledger=led, identity=AgentIdentity.generate())
    assert rep["applied"] is True
    assert "EVOLVE_HARNESS" in [b["action_type"] for b in led.blocks()]
    assert led.verify().valid
