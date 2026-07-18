"""Self-evolving harness: the runtime improves its own routing from experience.

Athena already synthesizes tools and heals skills at the *object* level. This is
the *meta* level — the harness tunes its own configuration from episode outcomes —
and, crucially, it cannot silently degrade: every proposed mutation is accepted
only if it improves a measurable metric on the recorded episodes, it is signed to
the ledger (EVOLVE), and it is reversible.

v1 evolves the tier router. Each finished task is an episode (directive, tier used,
success, how many specialists worked it). From the outcome the harness infers the
tier the task *should* have taken — a fast/medium run that failed or had to escalate
was under-powered (bump up); a full run a single specialist finished cleanly was
over-powered (drop to medium). Mis-tiered directives become candidate *learned
exemplars* for the correct tier. The candidate is committed only if replaying every
recorded episode through the router shows a net routing-accuracy gain.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import tier_router

_ORDER = ("fast", "medium", "full")


def _athena_home() -> Path:
    return Path(os.environ.get("ATHENA_HOME", Path.home() / ".athena"))


@dataclass
class Episode:
    directive: str
    tier: str            # the tier actually used
    success: bool
    score: float = 0.0
    n_roles: int = 0     # specialists that worked the task (full tier)
    escalated: bool = False
    ts: float = 0.0

    def ideal_tier(self) -> str:
        """The tier the outcome suggests this task should have taken."""
        if self.tier not in _ORDER:
            return self.tier
        idx = _ORDER.index(self.tier)
        # Under-powered: it failed (or had to escalate) below the top tier → go up.
        if (not self.success or self.escalated) and idx < len(_ORDER) - 1:
            return _ORDER[idx + 1]
        # Over-powered: a full run a single specialist finished cleanly → medium.
        if self.success and self.tier == "full" and self.n_roles <= 1:
            return "medium"
        return self.tier


class Evolver:
    """Records episodes and evolves the router's learned exemplars, gated by a
    replay metric, ledger-signed, and reversible."""

    def __init__(self, root: str | os.PathLike | None = None, *, max_episodes: int = 1000) -> None:
        self.root = Path(root or (_athena_home() / "evolution"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.episodes_path = self.root / "episodes.jsonl"
        self.exemplars_path = self.root / "exemplars.json"
        self.mutations_path = self.root / "mutations.jsonl"
        self.prev_path = self.root / "exemplars.prev.json"
        self.max_episodes = max_episodes
        self.learned = self._load_exemplars()
        tier_router.set_learned_exemplars(self.learned)  # apply at startup

    # --- persistence -----------------------------------------------------

    def _load_exemplars(self) -> dict:
        if self.exemplars_path.exists():
            try:
                d = json.loads(self.exemplars_path.read_text())
                return {t: list(d.get(t, [])) for t in _ORDER}
            except (json.JSONDecodeError, OSError):
                pass
        return {t: [] for t in _ORDER}

    def _save_exemplars(self, mapping: dict) -> None:
        tmp = self.exemplars_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(mapping, indent=2))
        os.replace(tmp, self.exemplars_path)

    # --- recording -------------------------------------------------------

    def record(self, directive: str, tier: str, success: bool, *, score: float = 0.0,
               n_roles: int = 0, escalated: bool = False) -> Episode:
        ep = Episode(
            directive=(directive or "")[:400], tier=tier, success=bool(success),
            score=float(score or 0.0), n_roles=int(n_roles or 0),
            escalated=bool(escalated), ts=time.time(),
        )
        with self.episodes_path.open("a") as f:
            f.write(json.dumps(asdict(ep)) + "\n")
        return ep

    def episodes(self) -> list[Episode]:
        if not self.episodes_path.exists():
            return []
        keys = {f.name for f in fields(Episode)}
        out: list[Episode] = []
        for line in self.episodes_path.read_text().splitlines()[-self.max_episodes:]:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                out.append(Episode(**{k: d[k] for k in keys if k in d}))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    # --- metric + proposal ----------------------------------------------

    @staticmethod
    def _accuracy(episodes: list[Episode], exemplars: dict) -> float:
        if not episodes:
            return 0.0
        with tier_router.using_learned(exemplars):
            correct = sum(1 for ep in episodes if tier_router.route_tier(ep.directive) == ep.ideal_tier())
        return correct / len(episodes)

    def _proposed(self, episodes: list[Episode]) -> dict:
        cand = {t: list(self.learned.get(t, [])) for t in _ORDER}
        seen = {t: set(cand[t]) for t in _ORDER}
        for ep in episodes:
            ideal = ep.ideal_tier()
            if ideal != ep.tier and ep.directive and ep.directive not in seen[ideal]:
                cand[ideal].append(ep.directive)
                seen[ideal].add(ep.directive)
        return cand

    # --- evolve / revert -------------------------------------------------

    def evolve(self, *, ledger=None, identity=None) -> dict:
        """Propose + gate + (maybe) commit one evolution of the router."""
        eps = self.episodes()
        if not eps:
            return {"applied": False, "reason": "no episodes recorded yet"}
        baseline = self._accuracy(eps, self.learned)
        candidate = self._proposed(eps)
        if candidate == self.learned:
            return {"applied": False, "reason": "nothing new to learn", "accuracy": round(baseline, 4)}
        improved = self._accuracy(eps, candidate)
        if improved <= baseline:
            return {
                "applied": False, "reason": "candidate did not improve routing accuracy",
                "accuracy": round(baseline, 4), "candidate_accuracy": round(improved, 4),
            }
        # Commit: snapshot for rollback, persist, live-update the router, sign.
        self.prev_path.write_text(json.dumps(self.learned))
        self.learned = candidate
        self._save_exemplars(candidate)
        tier_router.set_learned_exemplars(candidate)
        mutation = {
            "ts": time.time(), "kind": "router_exemplars",
            "baseline_accuracy": round(baseline, 4), "accuracy": round(improved, 4),
            "learned_counts": {t: len(candidate[t]) for t in _ORDER},
            "episodes": len(eps),
        }
        with self.mutations_path.open("a") as f:
            f.write(json.dumps(mutation) + "\n")
        if ledger is not None and identity is not None:
            ledger.append(identity, "EVOLVE_HARNESS", mutation)
        return {"applied": True, **mutation}

    def revert(self, *, ledger=None, identity=None) -> dict:
        """Roll back the most recent evolution."""
        if not self.prev_path.exists():
            return {"reverted": False, "reason": "nothing to revert"}
        prev = json.loads(self.prev_path.read_text())
        self.learned = {t: list(prev.get(t, [])) for t in _ORDER}
        self._save_exemplars(self.learned)
        tier_router.set_learned_exemplars(self.learned)
        self.prev_path.unlink()
        payload = {"kind": "revert", "learned_counts": {t: len(self.learned[t]) for t in _ORDER}}
        with self.mutations_path.open("a") as f:
            f.write(json.dumps({"ts": time.time(), **payload}) + "\n")
        if ledger is not None and identity is not None:
            ledger.append(identity, "EVOLVE_HARNESS", payload)
        return {"reverted": True, **payload}

    def status(self) -> dict:
        eps = self.episodes()
        return {
            "episodes": len(eps),
            "accuracy": round(self._accuracy(eps, self.learned), 4) if eps else None,
            "learned": {t: len(self.learned.get(t, [])) for t in _ORDER},
            "can_revert": self.prev_path.exists(),
            "mutations": self._mutation_log(),
        }

    def _mutation_log(self, limit: int = 10) -> list[dict]:
        if not self.mutations_path.exists():
            return []
        out = []
        for line in self.mutations_path.read_text().splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
