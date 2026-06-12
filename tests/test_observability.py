"""Phase 5.3: metrics registry + Prometheus exposition."""

from __future__ import annotations

from core.observability import Metrics


def test_counter_inc_and_value():
    m = Metrics()
    m.inc("swarm_tasks_total", outcome="success")
    m.inc("swarm_tasks_total", outcome="success")
    m.inc("swarm_tasks_total", outcome="incomplete")
    assert m.value("swarm_tasks_total", outcome="success") == 2
    assert m.value("swarm_tasks_total", outcome="incomplete") == 1
    assert m.total("swarm_tasks_total") == 3


def test_gauge_set_overwrites():
    m = Metrics()
    m.set("eval_pass_rate", 0.5)
    m.set("eval_pass_rate", 1.0)
    assert m.value("eval_pass_rate") == 1.0


def test_observe_duration_sum_count():
    m = Metrics()
    m.observe_duration("swarm_task_duration", 1.5)
    m.observe_duration("swarm_task_duration", 0.5)
    assert m.value("swarm_task_duration_seconds_sum") == 2.0
    assert m.value("swarm_task_duration_seconds_count") == 2.0


def test_prometheus_exposition_format():
    m = Metrics()
    m.inc("llm_calls_total", 3)
    m.inc("swarm_tasks_total", outcome="success")
    m.set("eval_pass_rate", 1.0)
    text = m.render_prometheus()
    assert "llm_calls_total 3" in text
    assert 'swarm_tasks_total{outcome="success"} 1' in text
    assert "eval_pass_rate 1.0" in text
    assert text.endswith("\n")


def test_reset_clears():
    m = Metrics()
    m.inc("x")
    m.reset()
    assert m.value("x") == 0.0
