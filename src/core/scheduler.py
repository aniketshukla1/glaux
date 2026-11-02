"""Scheduled jobs — run a directive through the swarm on a recurring cadence.

A job is a ``{directive, schedule}`` pair. The schedule is a standard 5-field
cron expression (``minute hour day month weekday``), a ``@hourly/@daily/...``
alias, or a simple ``every 30m`` interval. A background thread ticks once a
tick interval, dispatches any due jobs through the same swarm path as a manual
task (so each run is signed onto the ledger), and records the outcome.

Cron parsing is stdlib-only — no third-party dependency.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional


# --- schedule parsing -----------------------------------------------------

_ALIASES = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}

_UNIT_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
}

_MIN_INTERVAL_SECONDS = 10


def _parse_field(field_str: str, lo: int, hi: int) -> set[int]:
    vals: set[int] = set()
    for part in field_str.split(","):
        step = 1
        rng = part
        if "/" in part:
            rng, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError(f"bad step in {part!r}")
        if rng == "*":
            start, end = lo, hi
        elif "-" in rng:
            a, b = rng.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(rng)
        if start < lo or end > hi or start > end:
            raise ValueError(f"value out of range in {part!r} (expected {lo}-{hi})")
        vals.update(range(start, end + 1, step))
    if not vals:
        raise ValueError(f"empty field {field_str!r}")
    return vals


class CronExpr:
    """A 5-field cron expression: minute hour day-of-month month day-of-week."""

    def __init__(self, expr: str) -> None:
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError("cron needs 5 fields: 'minute hour day month weekday' (e.g. '0 9 * * *')")
        self.expr = expr
        self.minute = _parse_field(parts[0], 0, 59)
        self.hour = _parse_field(parts[1], 0, 23)
        self.dom = _parse_field(parts[2], 1, 31)
        self.month = _parse_field(parts[3], 1, 12)
        self.dow = _parse_field(parts[4], 0, 6)  # 0 = Sunday
        self._dom_restricted = parts[2] != "*"
        self._dow_restricted = parts[4] != "*"

    def matches(self, t: dt.datetime) -> bool:
        if t.minute not in self.minute or t.hour not in self.hour or t.month not in self.month:
            return False
        cron_dow = (t.weekday() + 1) % 7  # py Mon=0..Sun=6 -> cron Sun=0..Sat=6
        dom_ok = t.day in self.dom
        dow_ok = cron_dow in self.dow
        if self._dom_restricted and self._dow_restricted:
            return dom_ok or dow_ok  # standard Vixie-cron OR semantics
        if self._dom_restricted:
            return dom_ok
        if self._dow_restricted:
            return dow_ok
        return True

    def next_after(self, t: dt.datetime) -> dt.datetime:
        t = t.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
        for _ in range(366 * 24 * 60):
            if self.matches(t):
                return t
            t += dt.timedelta(minutes=1)
        raise ValueError("no matching time within a year")


class IntervalSchedule:
    def __init__(self, seconds: int) -> None:
        if seconds < _MIN_INTERVAL_SECONDS:
            raise ValueError(f"interval must be at least {_MIN_INTERVAL_SECONDS}s")
        self.seconds = seconds

    def matches(self, t: dt.datetime) -> bool:  # interval uses next_after only
        return False

    def next_after(self, t: dt.datetime) -> dt.datetime:
        return t + dt.timedelta(seconds=self.seconds)


def parse_schedule(spec: str):
    """Parse a schedule spec into something with ``next_after(dt)``. Raises
    ``ValueError`` on anything unrecognized."""
    s = (spec or "").strip()
    if not s:
        raise ValueError("schedule is required")
    if s.lower() in _ALIASES:
        return CronExpr(_ALIASES[s.lower()])
    m = re.fullmatch(r"every\s+(\d+)\s*([a-z]+)", s, re.IGNORECASE)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        if unit not in _UNIT_SECONDS:
            raise ValueError(f"unknown interval unit {unit!r}")
        return IntervalSchedule(n * _UNIT_SECONDS[unit])
    return CronExpr(s)  # otherwise treat as a cron expression


# --- jobs + scheduler -----------------------------------------------------


@dataclass
class Job:
    id: str
    directive: str
    schedule: str
    enabled: bool = True
    created_at: str = ""
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    last_status: Optional[str] = None  # ok | error | running
    last_result: Optional[str] = None
    run_count: int = 0


def _summarize(result) -> Optional[str]:
    if result is None:
        return None
    if isinstance(result, str):
        return result[:300]
    if isinstance(result, dict):
        text = result.get("final") or result.get("summary") or json.dumps(result)
        return str(text)[:300]
    return str(result)[:300]


class Scheduler:
    """Owns the set of scheduled jobs and a background tick thread."""

    def __init__(
        self,
        run_fn: Optional[Callable[[str], object]] = None,
        store_path: Optional[Path] = None,
        tick: float = 20.0,
    ) -> None:
        self.run_fn = run_fn
        self.store_path = Path(store_path) if store_path else None
        self.tick = tick
        self.jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def _now(self) -> dt.datetime:
        return dt.datetime.now().replace(microsecond=0)

    # -- management --
    def add(self, directive: str, schedule: str) -> dict:
        if not directive.strip():
            raise ValueError("directive is required")
        sched = parse_schedule(schedule)  # validates; raises ValueError
        now = self._now()
        job = Job(
            id=uuid.uuid4().hex[:8],
            directive=directive.strip(),
            schedule=schedule.strip(),
            enabled=True,
            created_at=now.isoformat(),
            next_run=sched.next_after(now).isoformat(),
        )
        with self._lock:
            self.jobs[job.id] = job
            self.save()
        return asdict(job)

    def remove(self, job_id: str) -> bool:
        with self._lock:
            existed = self.jobs.pop(job_id, None) is not None
            if existed:
                self.save()
            return existed

    def set_enabled(self, job_id: str, enabled: bool) -> Optional[dict]:
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            job.enabled = enabled
            if enabled:
                job.next_run = parse_schedule(job.schedule).next_after(self._now()).isoformat()
            self.save()
            return asdict(job)

    def list(self) -> list[dict]:
        with self._lock:
            return [asdict(j) for j in self.jobs.values()]

    def run_now(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self.jobs.get(job_id)
        if job is None:
            return None
        return self._dispatch(job)

    # -- background loop --
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="glaux-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.tick):
            try:
                self.tick_once(self._now())
            except Exception:  # noqa: BLE001 - never let the loop die
                pass

    def tick_once(self, now: dt.datetime) -> list[str]:
        """Dispatch every job whose next_run is due. Returns the ids fired."""
        due: list[Job] = []
        with self._lock:
            for job in self.jobs.values():
                if job.enabled and job.next_run and dt.datetime.fromisoformat(job.next_run) <= now:
                    due.append(job)
        for job in due:
            self._dispatch(job, now)
        return [j.id for j in due]

    def _dispatch(self, job: Job, now: Optional[dt.datetime] = None) -> dict:
        now = now or self._now()
        with self._lock:
            job.last_status = "running"
            # advance next_run up front so a slow run can't double-fire this slot
            try:
                job.next_run = parse_schedule(job.schedule).next_after(now).isoformat()
            except ValueError:
                job.next_run = None
            self.save()
        status, summary = "ok", None
        try:
            result = self.run_fn(job.directive) if self.run_fn else None
            summary = _summarize(result)
        except Exception as e:  # noqa: BLE001 - record, don't crash the scheduler
            status, summary = "error", f"{type(e).__name__}: {e}"[:300]
        with self._lock:
            job.last_run = now.isoformat()
            job.last_status = status
            job.last_result = summary
            job.run_count += 1
            self.save()
            return asdict(job)

    # -- persistence --
    def save(self) -> None:
        if not self.store_path:
            return
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(json.dumps([asdict(j) for j in self.jobs.values()], indent=2))

    def load(self) -> None:
        if not self.store_path or not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        with self._lock:
            for d in data:
                try:
                    job = Job(**{k: d.get(k) for k in Job.__dataclass_fields__})
                    # recompute next_run on load so missed slots don't all fire at once
                    if job.enabled:
                        job.next_run = parse_schedule(job.schedule).next_after(self._now()).isoformat()
                    self.jobs[job.id] = job
                except (ValueError, TypeError):
                    continue
