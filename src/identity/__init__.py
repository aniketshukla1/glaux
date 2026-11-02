"""Glaux cryptographic identity layer.

Public API:
- :class:`AgentIdentity` — keypair, signing, rotation, persistence
- :func:`verify` — verify a signature against a public key
- :class:`RotationRecord` — signed key-rotation authorization
- :class:`CapabilityToken`, :func:`issue_token`, :func:`verify_token` — signed grants
- :class:`KeyRegistry` — rotation-aware "which key at time T" lookups
"""

from .canonical import canonical_bytes
from .keypair import AgentIdentity, RotationRecord, verify
from .registry import KeyRegistry, KeyWindow
from .tokens import CapabilityToken, issue_token, verify_token

__all__ = [
    "AgentIdentity",
    "RotationRecord",
    "verify",
    "canonical_bytes",
    "KeyRegistry",
    "KeyWindow",
    "CapabilityToken",
    "issue_token",
    "verify_token",
]
