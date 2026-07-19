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


def test_tune_budgets_raises_when_role_keeps_capping_and_failing(tmp_path):
    ev = Evolver(root=tmp_path)
    for _ in range(4):
        ev.record_roles([{"role": "coder", "success": False, "capped": True, "iters": 8, "sig": "max iterations reached"}])
    rep = ev.tune_budgets({"coder": 8})
    assert rep["applied"] is True and rep["changes"]["coder"] == 10
    assert ev.budget_overrides()["coder"] == 10


def test_tune_budgets_lowers_when_role_finishes_early(tmp_path):
    ev = Evolver(root=tmp_path)
    for _ in range(4):
        ev.record_roles([{"role": "writer", "success": True, "capped": False, "iters": 3, "sig": ""}])
    rep = ev.tune_budgets({"writer": 8})
    assert rep["applied"] is True and rep["changes"]["writer"] == 7


def test_tune_budgets_needs_min_samples(tmp_path):
    ev = Evolver(root=tmp_path)
    for _ in range(3):  # below the evidence threshold
        ev.record_roles([{"role": "coder", "success": False, "capped": True, "iters": 8, "sig": "x"}])
    assert ev.tune_budgets({"coder": 8})["applied"] is False


def test_learn_lessons_on_repeated_failures(tmp_path):
    ev = Evolver(root=tmp_path)
    for _ in range(3):
        ev.record_roles([{"role": "coder", "success": False, "capped": False, "iters": 5, "sig": "tool X not found"}])
    rep = ev.learn_lessons()
    assert rep["applied"] is True and rep["roles"]["coder"] == 1
    assert any("tool X not found" in le for le in ev.lessons_for()["coder"])


def test_distill_playbook_from_a_successful_multistep_run(tmp_path):
    from agents.playbook import Playbooks

    ev = Evolver(root=tmp_path)
    pb = Playbooks(root=tmp_path / "pb")
    ev.record("build and test a todo api", "full", success=True, n_roles=2, roles=["coder", "tester"])
    rep = ev.distill_playbooks(pb)
    assert rep["applied"] is True and len(rep["playbooks"]) == 1
    saved = pb.list()
    assert len(saved) == 1
    body = pb.read(saved[0]["slug"])["body"]
    assert "coder" in body and "tester" in body
    # a second distill of the same episode must not duplicate the playbook
    assert ev.distill_playbooks(pb)["applied"] is False


def test_auto_evolve_cadence(tmp_path):
    ev = Evolver(root=tmp_path)
    ev.set_auto(True, every=3)
    assert ev.should_autoevolve() is False
    ev.record("a", "fast", False)
    ev.record("b", "fast", False)
    assert ev.should_autoevolve() is False   # 2 < 3
    ev.record("c", "fast", False)
    assert ev.should_autoevolve() is True     # cadence hit → fires + resets
    assert ev.should_autoevolve() is False    # reset


def test_revert_undoes_the_last_mutation_across_stores(tmp_path):
    ev = Evolver(root=tmp_path)
    for _ in range(4):
        ev.record_roles([{"role": "coder", "success": False, "capped": True, "iters": 8, "sig": "x"}])
    ev.tune_budgets({"coder": 8})
    assert ev.budget_overrides()["coder"] == 10
    out = ev.revert()
    assert out["reverted"] is True and out["store"] == "budgets"
    assert ev.budget_overrides() == {}          # rolled back


def test_evolve_all_runs_every_operator(tmp_path):
    from agents.playbook import Playbooks

    ev = Evolver(root=tmp_path)
    pb = Playbooks(root=tmp_path / "pb")
    d = "what is a florb?"
    t0 = tier_router.route_tier(d)
    ev.record(d, t0, success=False)
    rep = ev.evolve_all(pb, current_budgets={})
    assert set(rep) == {"routing", "budgets", "lessons", "playbooks"}
    assert rep["routing"]["applied"] is True   # the mis-tier got learned


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
