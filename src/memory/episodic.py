"""Episodic memory: traces of past task executions. Ranked by recency-decay.

Compression folds a batch of old episodes into one condensed "lessons" record
(via a pluggable summarizer) and archives the originals — keeping the brain
from drowning in stale traces.
"""

from __future__ import annotations

from typing import Callable, Optional

from .base import MemoryStore
from .record import MemoryHit
from .retriever import RetrievalPolicy


class EpisodicMemory(MemoryStore):
    layer = "episodic"

    def __init__(self, db, embedder, tenant: str = "default") -> None:
        super().__init__(
            db,
            embedder,
            tenant,
            default_policy=RetrievalPolicy(recency_half_life_days=14.0, max_tokens=3000),
        )

    def log(
        self,
        goal: str,
        *,
        plan=None,
        steps=None,
        outcome: Optional[str] = None,
        success: Optional[bool] = None,
        cost_tokens: Optional[int] = None,
        duration_ms: Optional[int] = None,
        agent_signatures=None,
        task_id: Optional[str] = None,
        dedup: bool = False,
    ) -> str:
        text = goal if not outcome else f"{goal}\n{outcome}"
        metadata = {
            "kind": "episode",
            "goal": goal,
            "plan": plan,
            "steps": steps or [],
            "outcome": outcome,
            "success": success,
            "cost_tokens": cost_tokens,
            "duration_ms": duration_ms,
            "agent_signatures": agent_signatures or [],
            "task_id": task_id,
        }
        return self.add(text, metadata=metadata, id=task_id, dedup=dedup)

    def compress(
        self,
        hits: list[MemoryHit],
        summarizer: Callable[[list[str]], str],
        *,
        archive_originals: bool = True,
    ) -> str:
        """Summarize `hits` into a single 'lessons' record. Returns its id.

        `summarizer` maps the episode texts to a condensed string (an LLM in
        production; any callable in tests).
        """
        texts = [h.metadata.get("goal") or h.text for h in hits]
        summary = summarizer(texts)
        lessons_id = self.add(
            summary,
            metadata={
                "kind": "lessons",
                "compressed_from": [h.id for h in hits],
                "episode_count": len(hits),
            },
            dedup=False,
        )
        if archive_originals:
            for h in hits:
                self.archive(h)
        return lessons_id
