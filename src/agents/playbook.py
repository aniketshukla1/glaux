"""Playbooks: authored markdown instructions the swarm can consult on demand.

Distinct from *code* skills (SkillSynthesizer synthesizes executable Python that
runs in the sandbox). A playbook is human- or agent-*authored knowledge* — a
name, a one-line description, and a markdown body of steps/conventions. The swarm
lists the available playbooks, opens the relevant one, and follows it. This is the
knowledge-injection pattern deepagents calls "skills"; we call it a playbook to
avoid colliding with Athena's executable skills.

Stored as ``<ATHENA_HOME>/playbooks/<slug>.md`` with a small frontmatter block.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_MAX_BODY = 100_000


def _athena_home() -> Path:
    return Path(os.environ.get("ATHENA_HOME", Path.home() / ".athena"))


class PlaybookError(Exception):
    """A bad name or a missing playbook — surfaced to the agent as a tool error."""


def _parse(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER.match(text)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip().lower()] = v.strip()
    return meta, m.group(2)


class Playbooks:
    def __init__(self, root: str | os.PathLike | None = None) -> None:
        self.root = Path(root or (_athena_home() / "playbooks")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _slug(self, name: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
        if not s:
            raise PlaybookError("a playbook needs a name")
        return s

    def list(self) -> list[dict]:
        out = []
        for f in sorted(self.root.glob("*.md")):
            meta, _ = _parse(f.read_text(errors="replace"))
            out.append({"name": meta.get("name", f.stem), "slug": f.stem, "description": meta.get("description", "")})
        return out

    def read(self, name: str) -> dict:
        p = self.root / f"{self._slug(name)}.md"
        if not p.is_file():
            raise PlaybookError(f"no such playbook {name!r}")
        meta, body = _parse(p.read_text(errors="replace"))
        return {
            "name": meta.get("name", p.stem),
            "slug": p.stem,
            "description": meta.get("description", ""),
            "body": body.strip(),
        }

    def save(self, name: str, description: str = "", body: str = "") -> dict:
        slug = self._slug(name)
        if not isinstance(body, str) or len(body) > _MAX_BODY:
            raise PlaybookError(f"playbook body must be a string under {_MAX_BODY} chars")
        # Keep the display name single-line so it can't corrupt the frontmatter.
        name_line = str(name).replace("\n", " ").strip()
        desc_line = str(description).replace("\n", " ").strip()
        doc = f"---\nname: {name_line}\ndescription: {desc_line}\n---\n{body.strip()}\n"
        (self.root / f"{slug}.md").write_text(doc)
        return {"name": name_line, "slug": slug, "description": desc_line}

    def delete(self, name: str) -> dict:
        slug = self._slug(name)
        p = self.root / f"{slug}.md"
        if p.exists():
            p.unlink()
        return {"slug": slug, "deleted": True}


PLAYBOOK_TOOLS = ("list_playbooks", "open_playbook", "save_playbook")


def unregister_playbooks(client) -> None:
    for name in PLAYBOOK_TOOLS:
        client.unregister(name)


def register_playbooks(client, playbooks: Playbooks) -> None:
    """Expose the playbook tools on a LocalMCPClient so the swarm can discover and
    follow authored instructions (every call is signed to the ledger)."""
    client.register(
        "list_playbooks",
        "List authored playbooks (name + description) — reusable instructions the swarm can follow.",
        playbooks.list, {},
    )
    client.register(
        "open_playbook", "Read a playbook's full instructions by name, then follow them.",
        playbooks.read, {"name": "string"},
    )
    client.register(
        "save_playbook", "Save a new authored playbook (markdown instructions) for reuse.",
        playbooks.save,
        {"name": "string", "description": "string", "body": "string (markdown instructions)"},
    )
