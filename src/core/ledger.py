"""Cryptographic swarm ledger — thin Python ergonomics over a native core.

The entire tamper-evident log lives in the Rust `glaux_ledger` crate: block
assembly, canonicalization, Ed25519 signing, SHA-256 hashing, chain
verification, and JSONL persistence. This module only:

1. adapts the agent-facing API (`append(identity, action_type, payload_dict)`),
   pulling the signing key out of an :class:`AgentIdentity`; and
2. layers rotation-aware key-validity checks on top of the native crypto
   verification, using a :class:`identity.KeyRegistry`.

Because signing *and* verification happen in Rust against one canonicalization,
there is no Python/Rust canonical-bytes coupling to keep in sync.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Optional

import glaux_ledger

from identity import KeyRegistry
from identity.keypair import AgentIdentity

GENESIS_HASH = "0" * 64


class Action:
    """Conventional action types (the ledger accepts any string)."""

    THINK = "THINK"
    CALL_SKILL = "CALL_SKILL"
    CALL_AGENT = "CALL_AGENT"
    OBSERVATION = "EMIT_OBSERVATION"
    GRANT = "CAPABILITY_GRANT"
    REVOKE = "CAPABILITY_REVOKE"
    ROTATE = "KEY_ROTATION"
    APPROVAL = "REQUEST_APPROVAL"
    PLAN = "PLAN"
    REFLECT = "REFLECT"
    SYNTHESIZE = "SYNTHESIZE_SKILL"
    MCP_TOOL = "MCP_TOOL"
    COMPACT = "COMPACT_CONTEXT"
    EVOLVE = "EVOLVE_HARNESS"
    CACHE_HIT = "CACHE_HIT"


@dataclass
class LedgerVerification:
    valid: bool
    first_bad_index: int = -1
    reason: str = "ok"

    def __bool__(self) -> bool:
        return self.valid


class Ledger:
    def __init__(
        self,
        _native: Optional["glaux_ledger.Ledger"] = None,
        *,
        on_append=None,
    ) -> None:
        self._led = _native if _native is not None else glaux_ledger.Ledger()
        # optional callback(block_dict) fired after each append (e.g. live streaming)
        self.on_append = on_append
        # Serialize appends: the swarm runs independent plan branches concurrently,
        # and the hash chain must be extended one block at a time.
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._led)

    @property
    def head_hash(self) -> str:
        return self._led.head_hash()

    def append(
        self,
        identity: AgentIdentity,
        action_type: str,
        payload: dict,
        *,
        timestamp: Optional[float] = None,
    ) -> dict:
        """Sign and append a block for `identity`. Returns the block as a dict."""
        with self._lock:
            block_json = self._led.append(
                identity.agent_id,
                identity.public_key_b58,
                identity.signing_key_b58(),
                action_type,
                json.dumps(payload),
                timestamp,
            )
        block = json.loads(block_json)
        if self.on_append is not None:
            try:
                self.on_append(block)
            except Exception:
                pass  # streaming must never break the ledger write
        return block

    def verify(self, registry: Optional[KeyRegistry] = None) -> LedgerVerification:
        """Native crypto + chain verification, then optional rotation-aware
        check that each block's signing key was valid for its agent at that time."""
        ok, bad_index, reason = self._led.verify()
        if not ok:
            return LedgerVerification(False, bad_index, reason)

        if registry is not None:
            for b in json.loads(self._led.blocks_meta()):
                # blocks carry integer microseconds; key windows are in seconds
                ts = b["timestamp_us"] / 1_000_000
                if registry.key_at(b["agent_id"], ts) != b["signing_pubkey"]:
                    return LedgerVerification(
                        False, b["index"], "signing key not valid for agent at block time"
                    )

        return LedgerVerification(True, -1, "ok")

    def blocks(self) -> list[dict]:
        """Per-block metadata (no payload) — for auditing/UI."""
        return json.loads(self._led.blocks_meta())

    def block(self, index: int) -> dict:
        """Full block including payload."""
        return json.loads(self._led.block(index))

    def block_json(self, index: int) -> str:
        """The block exactly as the native kernel canonicalizes it.

        Use this for anything that must stay verifiable — never
        ``json.dumps(block(i))``. Block hashes are computed over the serialized
        form, and Python and Rust can pick different (both valid) shortest
        representations of the same f64: Rust writes 1785527751.8959339 where
        Python writes 1785527751.895934. The value round-trips, the bytes do
        not, and the chain then fails to verify at that block.
        """
        return self._led.block(index)

    def save(self, path) -> None:
        """Write the chain to a sibling file, then rename it over ``path``.

        A kill mid-write leaves the previous chain intact, not a truncated file
        that ``load`` rejects (the API would then start from an empty chain).
        """
        tmp = f"{path}.tmp"
        with self._lock:  # one save at a time: they share the temp file
            self._led.save(tmp)
            os.replace(tmp, path)

    @classmethod
    def load(cls, path) -> "Ledger":
        return cls(_native=glaux_ledger.Ledger.load(str(path)))
