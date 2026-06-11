"""Skill library: curation and lifecycle over procedural memory.

A synthesized skill enters **quarantined**. Each real use is recorded; after
enough successes it is **promoted**, and if its success rate falls too low it is
**deprecated**. Near-duplicate skills become new *versions* (linked by
`parent_skill_id`) rather than siblings, so the library doesn't fill with
slight variations of the same thing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from memory.procedural import ProceduralMemory

from .synthesize import SkillCandidate

QUARANTINED = "quarantined"
PROMOTED = "promoted"
DEPRECATED = "deprecated"


@dataclass
class SkillRecord:
    id: str
    name: str
    description: str
    code: str
    entrypoint: str
    caps: dict
    status: str
    version: int
    parent_skill_id: Optional[str]
    usage_count: int
    success_count: int
    success_rate: float

    @classmethod
    def from_metadata(cls, rec_id: str, meta: dict) -> "SkillRecord":
        return cls(
            id=rec_id,
            name=meta.get("name", rec_id),
            description=meta.get("description", ""),
            code=meta.get("code", ""),
            entrypoint=meta.get("entrypoint", "run"),
            caps=meta.get("caps", {}),
            status=meta.get("status", QUARANTINED),
            version=int(meta.get("version", 1)),
            parent_skill_id=meta.get("parent_skill_id"),
            usage_count=int(meta.get("usage_count", 0)),
            success_count=int(meta.get("success_count", 0)),
            success_rate=float(meta.get("success_rate", 0.0)),
        )


class SkillLibrary:
    def __init__(
        self,
        procedural: ProceduralMemory,
        *,
        promote_after: int = 3,
        min_uses_for_deprecation: int = 3,
        deprecate_below: float = 0.5,
        version_threshold: float = 0.9,
    ) -> None:
        self.procedural = procedural
        self.promote_after = promote_after
        self.min_uses = min_uses_for_deprecation
        self.deprecate_below = deprecate_below
        self.version_threshold = version_threshold

    # --- storage ---------------------------------------------------------

    def _store(self, rec_id: Optional[str], meta: dict) -> str:
        text = f"{meta['name']}: {meta.get('description', '')}"
        return self.procedural.add(text, metadata=meta, id=rec_id, dedup=False)

    def add_candidate(self, candidate: SkillCandidate) -> SkillRecord:
        """Store a freshly synthesized skill as quarantined; version it if a
        near-duplicate already exists."""
        parent_id = None
        version = 1
        similar = self.procedural.search(f"{candidate.name} {candidate.description}", k=1)
        if similar and similar[0].similarity >= self.version_threshold:
            parent_id = similar[0].id
            version = int(similar[0].metadata.get("version", 1)) + 1

        meta = {
            "kind": "skill",
            "name": candidate.name,
            "description": candidate.description,
            "code": candidate.code,
            "entrypoint": candidate.entrypoint,
            "caps": candidate.caps,
            "tests": candidate.tests,
            "status": QUARANTINED,
            "version": version,
            "parent_skill_id": parent_id,
            "usage_count": 0,
            "success_count": 0,
            "success_rate": 0.0,
            "created_at": time.time(),
        }
        skill_id = self._store(None, meta)
        return SkillRecord.from_metadata(skill_id, meta)

    # --- lifecycle -------------------------------------------------------

    def get(self, skill_id: str) -> Optional[SkillRecord]:
        for hit in self.procedural.list_all():
            if hit.id == skill_id:
                return SkillRecord.from_metadata(hit.id, hit.metadata)
        return None

    def record_use(self, skill_id: str, success: bool) -> Optional[SkillRecord]:
        """Update counters and transition status (promote/deprecate)."""
        current = self.get(skill_id)
        if current is None:
            return None

        usage = current.usage_count + 1
        successes = current.success_count + (1 if success else 0)
        rate = successes / usage
        status = current.status
        if status == QUARANTINED and successes >= self.promote_after:
            status = PROMOTED
        if usage >= self.min_uses and rate < self.deprecate_below:
            status = DEPRECATED

        meta = {
            "kind": "skill",
            "name": current.name,
            "description": current.description,
            "code": current.code,
            "entrypoint": current.entrypoint,
            "caps": current.caps,
            "status": status,
            "version": current.version,
            "parent_skill_id": current.parent_skill_id,
            "usage_count": usage,
            "success_count": successes,
            "success_rate": rate,
        }
        self._store(skill_id, meta)
        return SkillRecord.from_metadata(skill_id, meta)

    def list(self, status: Optional[str] = None) -> list[SkillRecord]:
        records = [
            SkillRecord.from_metadata(h.id, h.metadata)
            for h in self.procedural.list_all()
            if h.metadata.get("kind") == "skill"
        ]
        if status is not None:
            records = [r for r in records if r.status == status]
        records.sort(key=lambda r: (-r.success_rate, r.name))
        return records
