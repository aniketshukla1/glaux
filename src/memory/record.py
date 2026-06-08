"""Shared memory record shapes.

Every stored record carries a `schema_version` (the forward-migration
invariant) plus a common envelope: the embeddable `text`, timestamps, tenant,
layer, and usage counters. Layer-specific fields are merged on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSION = 1


@dataclass
class MemoryHit:
    """A retrieved record. `similarity` is the raw cosine; `score` is the
    post-policy ranking score (recency/success-weighted)."""

    id: str
    similarity: float
    text: str
    metadata: dict
    namespace: str
    score: float = 0.0
