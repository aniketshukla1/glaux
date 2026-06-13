"""Scheduled jobs: cron/interval parsing and the scheduler lifecycle."""

from __future__ import annotations

import datetime as dt

import pytest

from core.scheduler import CronExpr, IntervalSchedule, Scheduler, parse_schedule


# --- schedule parsing ----------------------------------------------------


def test_parse_aliases_and_interval():
    assert isinstance(parse_schedule("@daily"), CronExpr)
    assert isinstance(parse_schedule("0 9 * * *"), CronExpr)
    iv = parse_schedule("every 30m")
    assert isinstance(iv, IntervalSchedule) and iv.seconds == 1800
    assert parse_schedule("every 2h").seconds == 7200


@pytest.mark.parametrize("bad", ["", "0 9 * *", "61 * * * *", "garbage", "every 0s", "*/0 * * * *"])
def test_parse_rejects_bad_specs(bad):
    with pytest.raises(ValueError):
        parse_schedule(bad)


def test_cron_matches_daily_9am():
    c = CronExpr("0 9 * * *")
    assert c.matches(dt.datetime(2026, 6, 13, 9, 0))
    assert not c.matches(dt.datetime(2026, 6, 13, 9, 1))
    assert not c.matches(dt.datetime(2026, 6, 13, 10, 0))


def test_cron_next_after():
    c = CronExpr("0 9 * * *")
    nxt = c.next_after(dt.datetime(2026, 6, 13, 12, 0))
    assert nxt == dt.datetime(2026, 6, 14, 9, 0)  # next 9am is tomorrow


def test_cron_step_field():
    c = CronExpr("*/15 * * * *")
    assert {m for m in range(60) if c.matches(dt.datetime(2026, 6, 13, 0, m))} == {0, 15, 30, 45}


def test_cron_weekday():
    # Sundays only (cron dow 0). 2026-06-14 is a Sunday.
    c = CronExpr("0 0 * * 0")
    assert c.matches(dt.datetime(2026, 6, 14, 0, 0))
    assert not c.matches(dt.datetime(2026, 6, 15, 0, 0))  # Monday


# --- scheduler -----------------------------------------------------------


def test_add_list_remove(tmp_path):
    s = Scheduler(run_fn=lambda d: {"final": "ok"}, store_path=tmp_path / "sched.json")
    job = s.add("summarize the news", "@daily")
    assert job["directive"] == "summarize the news" and job["next_run"]
    assert len(s.list()) == 1
    assert s.remove(job["id"]) is True
    assert s.list() == []
    assert s.remove("missing") is False


def test_add_rejects_bad_schedule(tmp_path):
    s = Scheduler(store_path=tmp_path / "sched.json")
    with pytest.raises(ValueError):
        s.add("do it", "not a cron")


def test_tick_dispatches_due_jobs(tmp_path):
    calls = []
    s = Scheduler(run_fn=lambda d: calls.append(d) or {"final": f"done:{d}"}, store_path=tmp_path / "s.json")
    job = s.add("daily report", "@daily")
    # force it due
    s.jobs[job["id"]].next_run = (dt.datetime.now() - dt.timedelta(minutes=1)).isoformat()

    fired = s.tick_once(dt.datetime.now())
    assert fired == [job["id"]]
    assert calls == ["daily report"]
    j = s.list()[0]
    assert j["last_status"] == "ok" and j["run_count"] == 1
    assert j["last_result"] == "done:daily report"
    # next_run advanced into the future
    assert dt.datetime.fromisoformat(j["next_run"]) > dt.datetime.now()


def test_disabled_jobs_do_not_fire(tmp_path):
    calls = []
    s = Scheduler(run_fn=lambda d: calls.append(d), store_path=tmp_path / "s.json")
    job = s.add("x", "@daily")
    s.set_enabled(job["id"], False)
    s.jobs[job["id"]].next_run = (dt.datetime.now() - dt.timedelta(minutes=1)).isoformat()
    assert s.tick_once(dt.datetime.now()) == []
    assert calls == []


def test_run_now_and_error_capture(tmp_path):
    def boom(_d):
        raise RuntimeError("kaboom")

    s = Scheduler(run_fn=boom, store_path=tmp_path / "s.json")
    job = s.add("explode", "@daily")
    out = s.run_now(job["id"])
    assert out["last_status"] == "error" and "kaboom" in out["last_result"]
    assert out["run_count"] == 1


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "s.json"
    s = Scheduler(run_fn=lambda d: None, store_path=path)
    s.add("nightly backup", "0 3 * * *")
    s2 = Scheduler(run_fn=lambda d: None, store_path=path)
    s2.load()
    jobs = s2.list()
    assert len(jobs) == 1 and jobs[0]["schedule"] == "0 3 * * *" and jobs[0]["next_run"]
