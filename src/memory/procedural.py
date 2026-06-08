"""Procedural memory: the skill library. Ranked by success rate.

Stores the schema Phase 4 (skill synthesis + curation) builds on: code, declared
capabilities, synthesized tests, version lineage, success rate, and lifecycle
status (quarantined → promoted → deprecated).
"""

from __future__ import annotations

from typing import Optional

from .base import MemoryStore
from .retriever import RetrievalPolicy


class ProceduralMemory(MemoryStore):
    layer = "procedural"

    def __init__(self, db, embedder, tenant: str = "default") -> None:
        super().__init__(
            db,
            embedder,
            tenant,
            default_policy=RetrievalPolicy(success_weight=2.0, max_tokens=4000),
        )

    def add_skill(
        self,
        name: str,
        code: str,
        *,
        description: Optional[str] = None,
        caps: Optional[dict] = None,
        tests: Optional[list] = None,
        version: int = 1,
        success_rate: float = 0.0,
        parent_skill_id: Optional[str] = None,
        status: str = "quarantined",
        skill_id: Optional[str] = None,
        dedup: bool = True,
    ) -> str:
        text = f"{name}: {description}" if description else name
        metadata = {
            "kind": "skill",
            "name": name,
            "code": code,
            "description": description,
            "caps": caps or {},
            "tests": tests or [],
            "version": version,
            "success_rate": success_rate,
            "parent_skill_id": parent_skill_id,
            "status": status,
        }
        return self.add(text, metadata=metadata, id=skill_id, dedup=dedup)
