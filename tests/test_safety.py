"""Phase 0.3: kill switch and dry-run mode."""

from __future__ import annotations

import pytest

import safety


@pytest.fixture(autouse=True)
def _reset_mode():
    safety.set_mode(None)
    yield
    safety.set_mode(None)


def test_default_is_live(monkeypatch):
    monkeypatch.delenv("GLAUX_SAFETY_MODE", raising=False)
    assert safety.current_mode() == safety.SafetyMode.LIVE
    assert safety.execution_allowed()


def test_env_var_sets_mode(monkeypatch):
    monkeypatch.setenv("GLAUX_SAFETY_MODE", "halted")
    assert safety.current_mode() == safety.SafetyMode.HALTED
    assert safety.is_halted()


def test_unknown_env_falls_back_to_live(monkeypatch):
    monkeypatch.setenv("GLAUX_SAFETY_MODE", "banana")
    assert safety.current_mode() == safety.SafetyMode.LIVE


def test_override_beats_env(monkeypatch):
    monkeypatch.setenv("GLAUX_SAFETY_MODE", "live")
    safety.set_mode("dry_run")
    assert safety.current_mode() == safety.SafetyMode.DRY_RUN
    assert safety.is_dry_run()
