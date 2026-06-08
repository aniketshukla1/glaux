"""Semantic memory: facts, configs, persistent context. Ranked by similarity."""

from __future__ import annotations

from typing import Optional

from .base import MemoryStore
from .retriever import RetrievalPolicy


class SemanticMemory(MemoryStore):
    layer = "semantic"

    def __init__(self, db, embedder, tenant: str = "default") -> None:
        super().__init__(
            db,
            embedder,
            tenant,
            default_policy=RetrievalPolicy(max_tokens=2000),
        )

    def add_fact(
        self,
        text: str,
        *,
        source: Optional[str] = None,
        id: Optional[str] = None,
        dedup: bool = True,
    ) -> str:
        metadata = {"kind": "fact"}
        if source:
            metadata["source"] = source
        return self.add(text, metadata=metadata, id=id, dedup=dedup)
