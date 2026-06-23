"""Observability: a tiny metrics registry + structured logging.

Dependency-free Prometheus exposition (counters/gauges + sum/count
"histograms") so the platform is scrapeable, plus one-line JSON event logs to
stdout. OpenTelemetry traces are a future addition (they need a collector to be
useful); these two cover the day-to-day "what is the swarm doing" questions.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict = defaultdict(float)
        self._gauges: dict = {}
        # Optional disk persistence so counters survive restarts (writes are
        # throttled so the request hot-path never blocks on file I/O).
        self._path: Optional[Path] = None
        self._save_interval = 5.0
        self._last_save = 0.0

    @staticmethod
    def _key(name: str, labels: dict):
        return (name, tuple(sorted(labels.items())))

    def inc(self, name: str, value: float = 1.0, **labels) -> None:
        with self._lock:
            self._counters[self._key(name, labels)] += float(value)
        self._maybe_save()

    def set(self, name: str, value: float, **labels) -> None:
        with self._lock:
            self._gauges[self._key(name, labels)] = float(value)
        self._maybe_save()

    def observe_duration(self, name: str, seconds: float) -> None:
        with self._lock:
            self._counters[self._key(f"{name}_seconds_sum", {})] += float(seconds)
            self._counters[self._key(f"{name}_seconds_count", {})] += 1.0
        self._maybe_save()

    def value(self, name: str, **labels) -> float:
        key = self._key(name, labels)
        with self._lock:
            if key in self._counters:
                return self._counters[key]
            return self._gauges.get(key, 0.0)

    def total(self, name: str) -> float:
        """Sum a metric across all label combinations."""
        with self._lock:
            return sum(
                v for (n, _l), v in self._counters.items() if n == name
            ) + sum(v for (n, _l), v in self._gauges.items() if n == name)

    def render_prometheus(self) -> str:
        with self._lock:
            items = list(self._counters.items()) + list(self._gauges.items())
        lines = []
        for (name, labels), v in sorted(items, key=lambda x: (x[0][0], x[0][1])):
            label_str = (
                "{" + ",".join(f'{k}="{val}"' for k, val in labels) + "}" if labels else ""
            )
            lines.append(f"{name}{label_str} {v}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()

    # -- persistence ------------------------------------------------------
    def bind(self, path) -> None:
        """Load any persisted metrics from `path` and enable throttled saving."""
        self._path = Path(path) if path else None
        self._load()
        self._last_save = time.monotonic()  # don't immediately rewrite what we just read

    def _load(self) -> None:
        if not self._path or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        with self._lock:
            for name, labels, v in data.get("counters", []):
                self._counters[self._key(name, dict(labels))] = float(v)
            for name, labels, v in data.get("gauges", []):
                self._gauges[self._key(name, dict(labels))] = float(v)

    def save(self) -> None:
        if not self._path:
            return
        with self._lock:
            payload = {
                "counters": [[n, list(labels), v] for (n, labels), v in self._counters.items()],
                "gauges": [[n, list(labels), v] for (n, labels), v in self._gauges.items()],
            }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload))
            tmp.replace(self._path)  # atomic
            self._last_save = time.monotonic()
        except OSError:
            pass

    def _maybe_save(self) -> None:
        if not self._path:
            return
        if time.monotonic() - self._last_save < self._save_interval:
            return
        self._last_save = time.monotonic()  # claim the slot before the slow write to avoid a stampede
        self.save()


METRICS = Metrics()


def log_json(event: str, **fields) -> None:
    """Emit one structured JSON log line to stdout."""
    record = {"ts": round(time.time(), 3), "event": event, **fields}
    print(json.dumps(record, default=str), file=sys.stdout, flush=True)
