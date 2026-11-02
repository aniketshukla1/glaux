"""User-defined sub-agents: custom specialists the router can dispatch to.

Glaux ships a fixed roster of specialists (see :mod:`agents.specialists`). This
lets a user define *their own* — a name, a one-line description the router reads to
decide when to use it, a system prompt, and a ReAct iteration budget — persisted as
JSON and merged into the roster when the swarm is built. deepagents lets you pass
custom subagents; this is Glaux's equivalent, kept auditable: each custom agent
gets a persisted cryptographic identity and signs the ledger like any specialist.

Stored as ``<GLAUX_HOME>/subagents.json``.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from paths import home

_MAX_PROMPT = 8000
_MAX_ITERS = 20


class CustomAgentError(Exception):
    """Invalid sub-agent definition — surfaced to the caller as a 400."""


class CustomAgents:
    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self.path = Path(path or (home() / "subagents.json"))
        self._agents = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                return data if isinstance(data, dict) else {}
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._agents, indent=2))
        os.replace(tmp, self.path)

    def _slug(self, name: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
        if not s:
            raise CustomAgentError("a sub-agent needs a name")
        return s

    def list(self) -> list[dict]:
        return [dict(v, slug=k) for k, v in sorted(self._agents.items())]

    def get(self, name: str) -> dict | None:
        slug = self._slug(name)
        v = self._agents.get(slug)
        return dict(v, slug=slug) if v else None

    def save(self, name: str, description: str = "", prompt: str = "", iterations: int = 8) -> dict:
        slug = self._slug(name)
        if not isinstance(prompt, str) or not prompt.strip():
            raise CustomAgentError("a sub-agent needs a system prompt")
        if len(prompt) > _MAX_PROMPT:
            raise CustomAgentError(f"system prompt too long (max {_MAX_PROMPT} chars)")
        try:
            iters = int(iterations)
        except (TypeError, ValueError):
            iters = 8
        iters = max(1, min(_MAX_ITERS, iters))
        rec = {
            "name": str(name).strip(),
            "description": str(description).replace("\n", " ").strip(),
            "prompt": prompt.strip(),
            "iterations": iters,
        }
        self._agents[slug] = rec
        self._save()
        return dict(rec, slug=slug)

    def delete(self, name: str) -> dict:
        slug = self._slug(name)
        self._agents.pop(slug, None)
        self._save()
        return {"slug": slug, "deleted": True}


def build_custom_specialists(
    store: CustomAgents, *, identities: dict, llm, reserved,
    budget_overrides=None, lessons=None, **kwargs,
) -> dict:
    """Turn saved specs into BaseAgents, keyed by slug, ready to merge into the swarm
    roster. Skips any slug that would shadow a built-in role, or that has no minted
    identity yet (the caller backfills identities first). The self-evolving harness
    may override the iteration budget and inject learned lessons per slug."""
    from .base import ACTION_INSTRUCTIONS, BaseAgent

    reserved = set(reserved)
    budget_overrides = budget_overrides or {}
    lessons = lessons or {}
    out: dict = {}
    for spec in store.list():
        slug = spec["slug"]
        if slug in reserved or slug not in identities:
            continue
        prompt = spec["prompt"] + "\n" + ACTION_INSTRUCTIONS
        if lessons.get(slug):
            prompt += "\n\nLEARNED LESSONS (from past runs — heed them):\n" + "\n".join(
                f"- {le}" for le in lessons[slug]
            )
        agent = BaseAgent(
            identity=identities[slug],
            llm=llm,
            name=slug,
            system_prompt=prompt,
            max_iterations=int(budget_overrides.get(slug) or spec.get("iterations", 8)),
            **kwargs,
        )
        # The router reads this to decide when to dispatch to this sub-agent.
        agent.description = spec.get("description") or f"custom sub-agent {slug}"
        out[slug] = agent
    return out
