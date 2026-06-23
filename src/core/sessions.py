"""Workspace model — projects and sessions (conversations).

A **session** is a conversation: an ordered list of runs (a directive the swarm
carried out, with its result and the signed blocks it produced). A **project**
groups sessions and can carry custom instructions. The active session is where
new tasks land. Everything persists to ``~/.athena/workspace.json`` so history
survives restarts.

This is an organizational layer over the existing swarm — the global signed
ledger is untouched; each run simply remembers the blocks it appended, so a
session is independently inspectable and re-verifiable.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

NEW_SESSION_TITLE = "New session"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return uuid.uuid4().hex[:8]


def _title_from(directive: str, limit: int = 52) -> str:
    t = " ".join((directive or "").split())
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


@dataclass
class Run:
    id: str
    directive: str
    final: Optional[str]
    success: bool
    cost: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)
    blocks: list = field(default_factory=list)
    created_at: str = ""
    model: str = ""  # the LLM model that produced this run (for per-turn metadata)
    canvas: Optional[dict] = None  # generative UI spec (A2UI), if the run produced one
    sources: list = field(default_factory=list)  # [{url, title}] the run actually browsed (citations)


@dataclass
class Session:
    id: str
    title: str
    project_id: Optional[str] = None
    persona_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    pinned: bool = False
    runs: list = field(default_factory=list)  # list[Run]


@dataclass
class Project:
    id: str
    name: str
    instructions: str = ""
    created_at: str = ""


@dataclass
class Persona:
    """A reusable, named system prompt — a custom assistant the user can apply to a chat."""
    id: str
    name: str
    instructions: str = ""
    emoji: str = "🧠"
    created_at: str = ""


class SessionStore:
    """Owns projects + sessions and tracks the active session."""

    def __init__(self, store_path: Optional[Path] = None) -> None:
        self.projects: dict[str, Project] = {}
        self.personas: dict[str, Persona] = {}
        self.sessions: dict[str, Session] = {}
        self.active_id: Optional[str] = None
        self.store_path = Path(store_path) if store_path else None

    # -- lifecycle --
    def ensure_active(self) -> Session:
        """Guarantee there's an active session (create a blank one if empty)."""
        if self.active_id and self.active_id in self.sessions:
            return self.sessions[self.active_id]
        if self.sessions:
            self.active_id = max(self.sessions.values(), key=lambda s: s.updated_at or s.created_at).id
            return self.sessions[self.active_id]
        return self.create_session()

    # -- projects --
    def create_project(self, name: str, instructions: str = "") -> dict:
        p = Project(id=_id(), name=name.strip() or "Untitled project", instructions=instructions, created_at=_now())
        self.projects[p.id] = p
        self.save()
        return asdict(p)

    def update_project(self, project_id: str, *, name: Optional[str] = None, instructions: Optional[str] = None) -> Optional[dict]:
        p = self.projects.get(project_id)
        if p is None:
            return None
        if name is not None:
            p.name = name.strip() or p.name
        if instructions is not None:
            p.instructions = instructions
        self.save()
        return asdict(p)

    def delete_project(self, project_id: str) -> bool:
        if project_id not in self.projects:
            return False
        del self.projects[project_id]
        for s in self.sessions.values():  # orphaned sessions go ungrouped
            if s.project_id == project_id:
                s.project_id = None
        self.save()
        return True

    # -- personas (reusable system prompts) --
    def create_persona(self, name: str, instructions: str = "", emoji: str = "🧠") -> dict:
        p = Persona(id=_id(), name=name.strip() or "Untitled persona", instructions=instructions,
                    emoji=(emoji or "🧠")[:4], created_at=_now())
        self.personas[p.id] = p
        self.save()
        return asdict(p)

    def update_persona(self, persona_id: str, *, name: Optional[str] = None,
                       instructions: Optional[str] = None, emoji: Optional[str] = None) -> Optional[dict]:
        p = self.personas.get(persona_id)
        if p is None:
            return None
        if name is not None:
            p.name = name.strip() or p.name
        if instructions is not None:
            p.instructions = instructions
        if emoji is not None:
            p.emoji = (emoji or "🧠")[:4]
        self.save()
        return asdict(p)

    def delete_persona(self, persona_id: str) -> bool:
        if persona_id not in self.personas:
            return False
        del self.personas[persona_id]
        for s in self.sessions.values():  # detach it from any chats using it
            if s.persona_id == persona_id:
                s.persona_id = None
        self.save()
        return True

    def persona_instructions_for(self, session_id: Optional[str]) -> str:
        s = self.sessions.get(session_id) if session_id else None
        if s is None or not s.persona_id:
            return ""
        p = self.personas.get(s.persona_id)
        return (p.instructions if p else "") or ""

    # -- sessions --
    def create_session(self, title: Optional[str] = None, project_id: Optional[str] = None) -> Session:
        if project_id is not None and project_id not in self.projects:
            project_id = None
        s = Session(
            id=_id(),
            title=(title or "").strip() or NEW_SESSION_TITLE,
            project_id=project_id,
            created_at=_now(),
            updated_at=_now(),
            runs=[],
        )
        self.sessions[s.id] = s
        self.active_id = s.id
        self.save()
        return s

    def activate(self, session_id: str) -> Optional[Session]:
        if session_id not in self.sessions:
            return None
        self.active_id = session_id
        self.save()
        return self.sessions[session_id]

    def active(self) -> Session:
        return self.ensure_active()

    def project_instructions_for(self, session_id: Optional[str]) -> str:
        """The custom instructions of the session's project (empty if none)."""
        s = self.sessions.get(session_id) if session_id else None
        if s is None or not s.project_id:
            return ""
        p = self.projects.get(s.project_id)
        return (p.instructions if p else "") or ""

    def update_session(self, session_id: str, *, title: Optional[str] = None,
                       project_id: Optional[str] = "_keep", persona_id: Optional[str] = "_keep") -> Optional[dict]:
        s = self.sessions.get(session_id)
        if s is None:
            return None
        if title is not None:
            s.title = title.strip() or s.title
        if project_id != "_keep":
            s.project_id = project_id if (project_id is None or project_id in self.projects) else s.project_id
        if persona_id != "_keep":
            s.persona_id = persona_id if (persona_id is None or persona_id in self.personas) else s.persona_id
        s.updated_at = _now()
        self.save()
        return self.session_meta(s)

    def set_pinned(self, session_id: str, pinned: bool) -> Optional[dict]:
        s = self.sessions.get(session_id)
        if s is None:
            return None
        s.pinned = bool(pinned)
        self.save()
        return self.session_meta(s)

    def search(self, query: str, limit: int = 25) -> list:
        """Find conversations whose title or message content matches `query`,
        returning each with a short snippet around the hit."""
        q = (query or "").strip().lower()
        if not q:
            return []
        out = []
        for s in self.sessions.values():
            if q in (s.title or "").lower():
                out.append({**self.session_meta(s), "snippet": s.title, "match": "title"})
                continue
            hit = None
            for r in s.runs:
                for text in (r.directive, r.final):
                    if text and q in str(text).lower():
                        hit = str(text)
                        break
                if hit:
                    break
            if hit:
                i = hit.lower().find(q)
                start = max(0, i - 30)
                snip = hit[start:i + len(q) + 60].strip().replace("\n", " ")
                out.append({**self.session_meta(s), "snippet": ("…" if start else "") + snip, "match": "content"})
        out.sort(key=lambda m: m.get("updated_at") or "", reverse=True)
        return out[:limit]

    def delete_session(self, session_id: str) -> bool:
        if session_id not in self.sessions:
            return False
        del self.sessions[session_id]
        if self.active_id == session_id:
            self.active_id = None
            self.ensure_active()
        self.save()
        return True

    def record_run(self, run: Run, session_id: Optional[str] = None) -> Session:
        s = self.sessions.get(session_id) if session_id else self.active()
        if s is None:
            s = self.active()
        run.id = run.id or _id()
        run.created_at = run.created_at or _now()
        s.runs.append(run)
        if s.title == NEW_SESSION_TITLE and run.directive:
            s.title = _title_from(run.directive)
        s.updated_at = _now()
        self.save()
        return s

    # -- serialization for the UI --
    def session_meta(self, s: Session) -> dict:
        last = s.runs[-1] if s.runs else None
        return {
            "id": s.id,
            "title": s.title,
            "project_id": s.project_id,
            "persona_id": s.persona_id,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "pinned": bool(s.pinned),
            "run_count": len(s.runs),
            "preview": (last.directive if last else None),
        }

    def tree(self) -> dict:
        self.ensure_active()
        sessions = sorted(
            self.sessions.values(),
            key=lambda s: (bool(s.pinned), s.updated_at or s.created_at),
            reverse=True,
        )
        return {
            "active_id": self.active_id,
            "projects": [asdict(p) for p in sorted(self.projects.values(), key=lambda p: p.created_at)],
            "personas": [asdict(p) for p in sorted(self.personas.values(), key=lambda p: p.created_at)],
            "sessions": [self.session_meta(s) for s in sessions],
        }

    def session_full(self, session_id: str) -> Optional[dict]:
        s = self.sessions.get(session_id)
        if s is None:
            return None
        d = asdict(s)
        d["run_count"] = len(s.runs)
        return d

    # -- persistence --
    def save(self) -> None:
        if not self.store_path:
            return
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "active_id": self.active_id,
            "projects": [asdict(p) for p in self.projects.values()],
            "personas": [asdict(p) for p in self.personas.values()],
            "sessions": [asdict(s) for s in self.sessions.values()],
        }
        self.store_path.write_text(json.dumps(data, indent=2))

    def load(self) -> None:
        if not self.store_path or not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        for pd in data.get("projects", []):
            try:
                self.projects[pd["id"]] = Project(**{k: pd[k] for k in Project.__dataclass_fields__ if k in pd})
            except (TypeError, KeyError):
                continue
        for pd in data.get("personas", []):
            try:
                self.personas[pd["id"]] = Persona(**{k: pd[k] for k in Persona.__dataclass_fields__ if k in pd})
            except (TypeError, KeyError):
                continue
        for sd in data.get("sessions", []):
            try:
                runs = [Run(**{k: rd[k] for k in Run.__dataclass_fields__ if k in rd}) for rd in sd.get("runs", [])]
                fields = {k: sd[k] for k in Session.__dataclass_fields__ if k != "runs" and k in sd}
                self.sessions[sd["id"]] = Session(**fields, runs=runs)
            except (TypeError, KeyError):
                continue
        self.active_id = data.get("active_id")
        self.ensure_active()
