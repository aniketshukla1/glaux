"""MemoryManager: the swarm's brain.

Owns one AthenaDB handle and one embedder, exposing the three memory layers
(semantic / episodic / procedural) as namespaces within that store. Because the
layers share a single AthenaDB instance, they share one embedding dimension —
so the whole manager uses one embedder.
"""

from __future__ import annotations

from typing import Optional

import athenadb

from .embedding import Embedder, HashingEmbedder
from .episodic import EpisodicMemory
from .procedural import ProceduralMemory
from .semantic import SemanticMemory


class MemoryManager:
    def __init__(
        self,
        path,
        *,
        embedder: Optional[Embedder] = None,
        tenant: str = "default",
    ) -> None:
        self.db = athenadb.AthenaDB(str(path))
        self.embedder = embedder or HashingEmbedder()
        self.tenant = tenant
        self.semantic = SemanticMemory(self.db, self.embedder, tenant)
        self.episodic = EpisodicMemory(self.db, self.embedder, tenant)
        self.procedural = ProceduralMemory(self.db, self.embedder, tenant)

    def snapshot(self) -> None:
        self.db.snapshot()

    def __len__(self) -> int:
        return len(self.db)
