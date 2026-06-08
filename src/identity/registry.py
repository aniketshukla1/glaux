"""Public key registry with rotation-aware validity windows.

The registry is the source of truth for "which public key was an agent using
at time T". This is what lets historical ledger blocks keep verifying after an
agent rotates its key: each key is valid only within a time window, and a
signature is checked against the key valid when the block was signed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .keypair import RotationRecord, verify


@dataclass
class KeyWindow:
    pubkey: str
    valid_from: float
    valid_to: Optional[float]  # None => still current (open-ended)

    def contains(self, ts: float) -> bool:
        if ts < self.valid_from:
            return False
        return self.valid_to is None or ts < self.valid_to


class KeyRegistry:
    """Tracks, per agent, the ordered sequence of public keys and the time
    window each was valid for."""

    def __init__(self) -> None:
        self._windows: dict[str, list[KeyWindow]] = {}

    def register_genesis(
        self, agent_id: str, pubkey: str, valid_from: float = 0.0
    ) -> None:
        """Record an agent's first (genesis) key. No-op if already known."""
        windows = self._windows.setdefault(agent_id, [])
        if not windows:
            windows.append(KeyWindow(pubkey, valid_from, None))

    def observe(self, agent_id: str, pubkey: str, valid_from: float = 0.0) -> None:
        """Auto-register an agent on first sighting of its action."""
        if not self._windows.get(agent_id):
            self.register_genesis(agent_id, pubkey, valid_from)

    def apply_rotation(self, record: RotationRecord) -> bool:
        """Apply a rotation record, closing the current key's window and opening
        the new key's. Returns False (and changes nothing) if the rotation is
        not authorized by the current key or its signature is invalid."""
        windows = self._windows.get(record.agent_id)
        if not windows:
            return False
        current = windows[-1]
        if current.valid_to is not None:
            return False  # there is no open current key
        if current.pubkey != record.old_pubkey:
            return False  # rotation must be authorized by the current key
        if not verify(record.old_pubkey, record.signing_payload(), record.signature):
            return False
        current.valid_to = record.rotated_at
        windows.append(KeyWindow(record.new_pubkey, record.rotated_at, None))
        return True

    def key_at(self, agent_id: str, ts: float) -> Optional[str]:
        """The public key the agent was using at time ``ts``, or None."""
        for w in self._windows.get(agent_id, []):
            if w.contains(ts):
                return w.pubkey
        return None

    def current_key(self, agent_id: str) -> Optional[str]:
        windows = self._windows.get(agent_id, [])
        return windows[-1].pubkey if windows else None

    def verify_rotation_chain(
        self, agent_id: str, genesis_pubkey: str, records: list[RotationRecord]
    ) -> bool:
        """Independently validate a full rotation chain from genesis, without
        mutating registry state. Each record must be signed by the preceding key
        and reference it as ``old_pubkey``."""
        expected_old = genesis_pubkey
        for rec in records:
            if rec.agent_id != agent_id:
                return False
            if rec.old_pubkey != expected_old:
                return False
            if not verify(rec.old_pubkey, rec.signing_payload(), rec.signature):
                return False
            expected_old = rec.new_pubkey
        return True
