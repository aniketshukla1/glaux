"""Base memory store: add / search / dedup / archive over one AthenaDB handle.

Each layer is a logical *namespace* inside a shared AthenaDB instance:
``namespace = f"{tenant}:{layer}"``. This partitions by both tenant and layer
at the engine level (AthenaDB filters by namespace), so the multi-tenant story
is a field, not a migration.

Note: AthenaDB keys entries by id globally, so "archiving" is simply an upsert
that moves a record to the `:archive` namespace — live-namespace searches stop
returning it, but it is not destroyed (forgetting is reversible).
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Optional

from .embedding import Embedder
from .record import SCHEMA_VERSION, MemoryHit
from .retriever import RetrievalPolicy, Reranker, apply_policy


class MemoryStore:
    layer = "base"

    def __init__(
        self,
        db,
        embedder: Embedder,
        tenant: str = "default",
        *,
        dedup_threshold: float = 0.95,
        default_policy: Optional[RetrievalPolicy] = None,
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.tenant = tenant
        self.namespace = f"{tenant}:{self.layer}"
        self.archive_namespace = f"{tenant}:{self.layer}:archive"
        self.dedup_threshold = dedup_threshold
        self.default_policy = default_policy or RetrievalPolicy()

    # --- writes ----------------------------------------------------------

    def add(
        self,
        text: str,
        metadata: Optional[dict] = None,
        *,
        id: Optional[str] = None,
        dedup: bool = True,
    ) -> str:
        """Embed and store `text`. If `dedup` and a near-identical record
        exists (cosine ≥ threshold), merge metadata into it instead of
        inserting a duplicate. Returns the record id."""
        vec = self.embedder.embed_one(text)
        now = time.time()

        if dedup:
            duplicate = self._find_duplicate(vec)
            if duplicate is not None:
                return self._merge(duplicate, metadata, now)

        rec_id = id or uuid.uuid4().hex
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "layer": self.layer,
            "tenant": self.tenant,
            "text": text,
            "created_at": now,
            "updated_at": now,
            "usage_count": 0,
            "last_used": None,
        }
        if metadata:
            envelope.update(metadata)
        self._upsert(rec_id, vec, envelope, self.namespace)
        return rec_id

    def _upsert(self, rec_id: str, vec: list[float], envelope: dict, namespace: str) -> None:
        self.db.add(
            ids=[rec_id],
            vectors=[vec],
            metadatas=[json.dumps(envelope)],
            namespace=namespace,
            embed_model_id=self.embedder.model_id,
        )

    def _find_duplicate(self, vec: list[float]):
        rows = self.db.query(vec, 1, self.namespace)
        if rows:
            rec_id, score, _ns, _model, meta_json = rows[0]
            if score >= self.dedup_threshold:
                return rec_id, json.loads(meta_json)
        return None

    def _merge(self, duplicate, new_metadata: Optional[dict], now: float) -> str:
        existing_id, meta = duplicate
        if new_metadata:
            meta.update(new_metadata)
        meta["updated_at"] = now
        meta["merge_count"] = int(meta.get("merge_count", 0)) + 1
        vec = self.embedder.embed_one(meta.get("text", ""))
        self._upsert(existing_id, vec, meta, self.namespace)
        return existing_id

    # --- reads -----------------------------------------------------------

    def candidates(self, query_text: str, n: int) -> list[MemoryHit]:
        qvec = self.embedder.embed_one(query_text)
        rows = self.db.query(qvec, n, self.namespace)
        hits = []
        for rec_id, score, ns, _model, meta_json in rows:
            meta = json.loads(meta_json)
            hits.append(
                MemoryHit(
                    id=rec_id,
                    similarity=score,
                    text=meta.get("text", ""),
                    metadata=meta,
                    namespace=ns,
                )
            )
        return hits

    def search(
        self,
        query_text: str,
        k: int = 5,
        *,
        policy: Optional[RetrievalPolicy] = None,
        reranker: Optional[Reranker] = None,
        now: Optional[float] = None,
    ) -> list[MemoryHit]:
        policy = policy or self.default_policy
        now = now if now is not None else time.time()
        n = max(k * max(policy.candidate_multiplier, 1), k)
        cands = self.candidates(query_text, n)
        return apply_policy(query_text, cands, k, policy, now, reranker)

    # --- hygiene ---------------------------------------------------------

    def archive(self, hit: MemoryHit) -> None:
        """Move a record to the archive namespace (reversible forgetting).
        Live searches stop returning it; the data is preserved."""
        meta = dict(hit.metadata)
        meta["archived_at"] = time.time()
        vec = self.embedder.embed_one(meta.get("text", hit.text))
        self._upsert(hit.id, vec, meta, self.archive_namespace)

    def restore(self, hit: MemoryHit) -> None:
        meta = dict(hit.metadata)
        meta.pop("archived_at", None)
        vec = self.embedder.embed_one(meta.get("text", hit.text))
        self._upsert(hit.id, vec, meta, self.namespace)

    def delete(self, ids: list[str]) -> int:
        return self.db.delete(ids)
