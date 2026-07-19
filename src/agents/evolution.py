"""Self-evolving harness: the runtime improves its own configuration from experience.

Athena already synthesizes tools and heals skills at the *object* level. This is the
*meta* level — the harness tunes its own configuration from episode outcomes — and,
crucially, it cannot silently degrade: every mutation is gated (only applied when the
evidence supports it), signed to the ledger (EVOLVE), and reversible.

Operators (each gated + signed + reversible):
  - routing   : learn tier-router exemplars from mis-tiered tasks (replay-accuracy gated)
  - budgets   : raise/lower a specialist's iteration budget from its cap-hit + failure rate
  - lessons   : attach a "you keep failing on X" note to a specialist's prompt
  - playbooks : distill a reusable playbook from a successful multi-specialist run

An optional auto-evolve cadence runs the operators every N recorded episodes.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import tier_router

_ORDER = ("fast", "medium", "full")

# Budget tuning bounds + evidence thresholds.
_MIN_ITERS, _MAX_ITERS = 4, 16
_BUDGET_MIN_SAMPLES = 4
_LESSON_MIN_COUNT = 3


def _athena_home() -> Path:
    return Path(os.environ.get("ATHENA_HOME", Path.home() / ".athena"))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")


@dataclass
class Episode:
    directive: str
    tier: str            # the tier actually used
    success: bool
    score: float = 0.0
    n_roles: int = 0     # specialists that worked the task (full tier)
    escalated: bool = False
    roles: list = field(default_factory=list)  # ordered plan roles (for distillation)
    ts: float = 0.0

    def ideal_tier(self) -> str:
        """The tier the outcome suggests this task should have taken."""
        if self.tier not in _ORDER:
            return self.tier
        idx = _ORDER.index(self.tier)
        if (not self.success or self.escalated) and idx < len(_ORDER) - 1:
            return _ORDER[idx + 1]                       # under-powered → up
        if self.success and self.tier == "full" and self.n_roles <= 1:
            return "medium"                              # over-powered → down
        return self.tier


class Evolver:
    """Records episodes + per-role outcomes and evolves the harness config, each
    mutation gated, ledger-signed, and reversible."""

    def __init__(self, root: str | os.PathLike | None = None, *, max_episodes: int = 1000) -> None:
        self.root = Path(root or (_athena_home() / "evolution"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.episodes_path = self.root / "episodes.jsonl"
        self.role_stats_path = self.root / "role_stats.jsonl"
        self.exemplars_path = self.root / "exemplars.json"
        self.budgets_path = self.root / "budgets.json"
        self.lessons_path = self.root / "lessons.json"
        self.auto_path = self.root / "auto.json"
        self.mutations_path = self.root / "mutations.jsonl"
        self.undo_path = self.root / "undo.jsonl"
        self.max_episodes = max_episodes
        self._since_auto = 0

        self.learned = {t: list(self._load_json(self.exemplars_path, {}).get(t, [])) for t in _ORDER}
        self.budgets = {k: int(v) for k, v in self._load_json(self.budgets_path, {}).items()}
        self.lessons = {k: list(v) for k, v in self._load_json(self.lessons_path, {}).items()}
        self.auto = {"enabled": False, "every": 10, **self._load_json(self.auto_path, {})}
        tier_router.set_learned_exemplars(self.learned)  # apply at startup

    # --- json helpers ----------------------------------------------------

    @staticmethod
    def _load_json(path: Path, default):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return default

    @staticmethod
    def _save_json(path: Path, data) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)

    def _save_exemplars(self, mapping: dict) -> None:
        self._save_json(self.exemplars_path, mapping)

    # --- recording -------------------------------------------------------

    def record(self, directive: str, tier: str, success: bool, *, score: float = 0.0,
               n_roles: int = 0, escalated: bool = False, roles=None) -> Episode:
        ep = Episode(
            directive=(directive or "")[:400], tier=tier, success=bool(success),
            score=float(score or 0.0), n_roles=int(n_roles or 0),
            escalated=bool(escalated), roles=list(roles or []), ts=time.time(),
        )
        with self.episodes_path.open("a") as f:
            f.write(json.dumps(asdict(ep)) + "\n")
        self._since_auto += 1
        return ep

    def record_roles(self, items) -> None:
        """Per-role step outcomes for budget/lesson tuning: {role, success, capped, iters, sig}."""
        if not items:
            return
        with self.role_stats_path.open("a") as f:
            for it in list(items)[:50]:
                f.write(json.dumps({
                    "role": it.get("role"), "success": bool(it.get("success")),
                    "capped": bool(it.get("capped")), "iters": int(it.get("iters") or 0),
                    "sig": (it.get("sig") or "")[:80],
                }) + "\n")

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

    def role_stats(self, limit: int = 4000) -> list[dict]:
        if not self.role_stats_path.exists():
            return []
        out = []
        for line in self.role_stats_path.read_text().splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    # --- config the swarm reads -----------------------------------------

    def budget_overrides(self) -> dict:
        return dict(self.budgets)

    def lessons_for(self) -> dict:
        return {k: list(v) for k, v in self.lessons.items()}

    # --- operator 1: routing (replay-accuracy gated) ---------------------

    @staticmethod
    def _accuracy(episodes: list[Episode], exemplars: dict) -> float:
        if not episodes:
            return 0.0
        with tier_router.using_learned(exemplars):
            correct = sum(1 for ep in episodes if tier_router.route_tier(ep.directive) == ep.ideal_tier())
        return correct / len(episodes)

    def _proposed_exemplars(self, episodes: list[Episode]) -> dict:
        cand = {t: list(self.learned.get(t, [])) for t in _ORDER}
        seen = {t: set(cand[t]) for t in _ORDER}
        for ep in episodes:
            ideal = ep.ideal_tier()
            if ideal != ep.tier and ep.directive and ep.directive not in seen[ideal]:
                cand[ideal].append(ep.directive)
                seen[ideal].add(ep.directive)
        return cand

    def evolve(self, *, ledger=None, identity=None) -> dict:
        """Operator: learn router exemplars. Committed only on a net accuracy gain."""
        eps = self.episodes()
        if not eps:
            return {"applied": False, "reason": "no episodes recorded yet", "kind": "router_exemplars"}
        baseline = self._accuracy(eps, self.learned)
        candidate = self._proposed_exemplars(eps)
        if candidate == self.learned:
            return {"applied": False, "reason": "nothing new to learn", "kind": "router_exemplars",
                    "accuracy": round(baseline, 4)}
        improved = self._accuracy(eps, candidate)
        if improved <= baseline:
            return {"applied": False, "reason": "candidate did not improve routing accuracy",
                    "kind": "router_exemplars", "accuracy": round(baseline, 4),
                    "candidate_accuracy": round(improved, 4)}
        self._push_undo({"store": "routing", "prev": {t: list(self.learned[t]) for t in _ORDER}})
        self.learned = candidate
        self._save_exemplars(candidate)
        tier_router.set_learned_exemplars(candidate)
        mutation = {
            "kind": "router_exemplars", "baseline_accuracy": round(baseline, 4),
            "accuracy": round(improved, 4), "learned_counts": {t: len(candidate[t]) for t in _ORDER},
            "episodes": len(eps),
        }
        self._log_mutation(mutation, ledger, identity)
        return {"applied": True, **mutation}

    # --- operator 2: iteration budgets (evidence gated) ------------------

    def _role_agg(self) -> dict:
        agg: dict = {}
        for r in self.role_stats():
            role = r.get("role")
            if not role:
                continue
            a = agg.setdefault(role, {"n": 0, "capped": 0, "capped_fail": 0, "iters_sum": 0})
            a["n"] += 1
            a["iters_sum"] += int(r.get("iters") or 0)
            if r.get("capped"):
                a["capped"] += 1
                if not r.get("success"):
                    a["capped_fail"] += 1
        return agg

    def tune_budgets(self, current_budgets: dict | None = None, *, ledger=None, identity=None) -> dict:
        """Operator: raise a role's iteration budget if it keeps hitting the cap and
        failing; lower it if it always finishes well under budget."""
        current_budgets = current_budgets or {}
        proposals: dict = {}
        for role, s in self._role_agg().items():
            if s["n"] < _BUDGET_MIN_SAMPLES:
                continue
            cur = self.budgets.get(role) or current_budgets.get(role) or 8
            avg = s["iters_sum"] / s["n"]
            if s["capped"] / s["n"] >= 0.4 and s["capped_fail"] >= 1:
                new = min(cur + 2, _MAX_ITERS)
            elif s["capped"] == 0 and avg <= cur - 3:
                new = max(cur - 1, _MIN_ITERS)
            else:
                continue
            if new != cur:
                proposals[role] = new
        if not proposals:
            return {"applied": False, "reason": "no budget changes warranted", "kind": "role_budgets"}
        self._push_undo({"store": "budgets", "prev": dict(self.budgets)})
        self.budgets.update(proposals)
        self._save_json(self.budgets_path, self.budgets)
        mutation = {"kind": "role_budgets", "changes": proposals}
        self._log_mutation(mutation, ledger, identity)
        return {"applied": True, **mutation}

    # --- operator 3: prompt lessons (evidence gated) ---------------------

    def learn_lessons(self, *, ledger=None, identity=None) -> dict:
        """Operator: when a role keeps failing the same way, attach a lesson to its prompt."""
        counts: dict = {}
        for r in self.role_stats():
            if r.get("success") or not r.get("sig") or not r.get("role"):
                continue
            counts[(r["role"], r["sig"])] = counts.get((r["role"], r["sig"]), 0) + 1
        additions: dict = {}
        for (role, sig), c in counts.items():
            if c < _LESSON_MIN_COUNT:
                continue
            lesson = f'In past runs you repeatedly failed with: "{sig}". Handle this case explicitly before finishing.'
            if lesson not in self.lessons.get(role, []):
                additions.setdefault(role, []).append(lesson)
        if not additions:
            return {"applied": False, "reason": "no recurring failures to learn from", "kind": "prompt_lesson"}
        self._push_undo({"store": "lessons", "prev": {k: list(v) for k, v in self.lessons.items()}})
        for role, ls in additions.items():
            self.lessons.setdefault(role, []).extend(ls)
        self._save_json(self.lessons_path, self.lessons)
        mutation = {"kind": "prompt_lesson", "roles": {r: len(ls) for r, ls in additions.items()}}
        self._log_mutation(mutation, ledger, identity)
        return {"applied": True, **mutation}

    # --- operator 4: playbook distillation (evidence gated) --------------

    @staticmethod
    def _playbook_name(directive: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+", directive or "")[:6]
        return (" ".join(words) or "distilled task").capitalize()

    @staticmethod
    def _distill_body(ep: Episode) -> str:
        steps = "\n".join(f"{i}. {role}" for i, role in enumerate(ep.roles, 1))
        return (
            f'Approach that worked for a task like: "{ep.directive}".\n\n'
            f"The swarm solved it with these specialists, in order:\n{steps}\n\n"
            "Reuse this sequence for similar tasks."
        )

    def distill_playbooks(self, playbooks, *, ledger=None, identity=None, max_new: int = 3) -> dict:
        """Operator: turn a successful multi-specialist run into a reusable playbook."""
        if playbooks is None:
            return {"applied": False, "reason": "playbooks store unavailable", "kind": "playbook_distilled"}
        existing = {p["slug"] for p in playbooks.list()}
        made: list = []
        for ep in reversed(self.episodes()):
            if len(made) >= max_new:
                break
            if not ep.success or len(ep.roles) < 2:
                continue
            name = self._playbook_name(ep.directive)
            slug = _slug(name)
            if not slug or slug in existing:
                continue
            playbooks.save(name, f"Learned from a successful {len(ep.roles)}-specialist run.", self._distill_body(ep))
            existing.add(slug)
            made.append(name)
        if not made:
            return {"applied": False, "reason": "no new multi-step successes to distill", "kind": "playbook_distilled"}
        # Distilled playbooks live in the Playbooks store — reversible by deleting them there.
        mutation = {"kind": "playbook_distilled", "playbooks": made}
        self._log_mutation(mutation, ledger, identity)
        return {"applied": True, **mutation}

    # --- run everything --------------------------------------------------

    def evolve_all(self, playbooks=None, *, current_budgets=None, ledger=None, identity=None) -> dict:
        return {
            "routing": self.evolve(ledger=ledger, identity=identity),
            "budgets": self.tune_budgets(current_budgets, ledger=ledger, identity=identity),
            "lessons": self.learn_lessons(ledger=ledger, identity=identity),
            "playbooks": self.distill_playbooks(playbooks, ledger=ledger, identity=identity),
        }

    # --- auto-evolve cadence ---------------------------------------------

    def set_auto(self, enabled: bool, every: int = 10) -> dict:
        self.auto = {"enabled": bool(enabled), "every": max(1, int(every or 10))}
        self._save_json(self.auto_path, self.auto)
        return self.auto

    def should_autoevolve(self) -> bool:
        if not self.auto.get("enabled"):
            return False
        if self._since_auto >= int(self.auto.get("every", 10)):
            self._since_auto = 0
            return True
        return False

    # --- undo / revert ---------------------------------------------------

    def _push_undo(self, entry: dict) -> None:
        with self.undo_path.open("a") as f:
            f.write(json.dumps({"ts": time.time(), **entry}) + "\n")

    def _undo_entries(self) -> list[dict]:
        if not self.undo_path.exists():
            return []
        out = []
        for line in self.undo_path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def can_revert(self) -> bool:
        return bool(self._undo_entries())

    def revert(self, *, ledger=None, identity=None) -> dict:
        """Roll back the most recent reversible mutation (routing / budgets / lessons)."""
        entries = self._undo_entries()
        if not entries:
            return {"reverted": False, "reason": "nothing to revert"}
        last = entries[-1]
        store, prev = last.get("store"), last.get("prev", {})
        if store == "routing":
            self.learned = {t: list(prev.get(t, [])) for t in _ORDER}
            self._save_exemplars(self.learned)
            tier_router.set_learned_exemplars(self.learned)
        elif store == "budgets":
            self.budgets = {k: int(v) for k, v in prev.items()}
            self._save_json(self.budgets_path, self.budgets)
        elif store == "lessons":
            self.lessons = {k: list(v) for k, v in prev.items()}
            self._save_json(self.lessons_path, self.lessons)
        else:
            return {"reverted": False, "reason": f"cannot revert {store!r}"}
        self._write_undo(entries[:-1])
        payload = {"kind": "revert", "store": store}
        self._log_mutation(payload, ledger, identity)
        return {"reverted": True, **payload}

    def _write_undo(self, entries: list[dict]) -> None:
        self.undo_path.write_text("".join(json.dumps(e) + "\n" for e in entries))

    # --- status / logging ------------------------------------------------

    def _log_mutation(self, mutation: dict, ledger, identity) -> None:
        rec = {"ts": time.time(), **mutation}
        with self.mutations_path.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        if ledger is not None and identity is not None:
            ledger.append(identity, "EVOLVE_HARNESS", rec)

    def _mutation_log(self, limit: int = 12) -> list[dict]:
        if not self.mutations_path.exists():
            return []
        out = []
        for line in self.mutations_path.read_text().splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def status(self) -> dict:
        eps = self.episodes()
        return {
            "episodes": len(eps),
            "accuracy": round(self._accuracy(eps, self.learned), 4) if eps else None,
            "learned": {t: len(self.learned.get(t, [])) for t in _ORDER},
            "budgets": dict(self.budgets),
            "lessons": {r: len(v) for r, v in self.lessons.items()},
            "auto": self.auto,
            "can_revert": self.can_revert(),
            "mutations": self._mutation_log(),
        }
