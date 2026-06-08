"""Capability tokens: signed, expiring grants between agents.

A capability token is how one agent authorizes another to do something
(e.g. accept a handoff, call a skill). The issuer signs it; the receiver
verifies it against the issuer's public key before acting. Tokens carry an
expiry and a nonce so they cannot be replayed indefinitely.
"""

from __future__ import annotations

import secrets as _secrets
import time
from dataclasses import dataclass
from typing import Optional

import base58

from .canonical import canonical_bytes
from .keypair import AgentIdentity, verify


@dataclass(frozen=True)
class CapabilityToken:
    issuer: str  # agent_id of the granting agent
    subject: str  # agent_id the grant is for
    capability: str  # opaque capability string, e.g. "call_agent:researcher"
    issued_at: float
    expires_at: float
    nonce: str
    signature: str  # base58, by the issuer's current key

    def signing_payload(self) -> bytes:
        return canonical_bytes(
            {
                "issuer": self.issuer,
                "subject": self.subject,
                "capability": self.capability,
                "issued_at": self.issued_at,
                "expires_at": self.expires_at,
                "nonce": self.nonce,
            }
        )

    def to_dict(self) -> dict:
        return {
            "issuer": self.issuer,
            "subject": self.subject,
            "capability": self.capability,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CapabilityToken":
        return cls(
            issuer=d["issuer"],
            subject=d["subject"],
            capability=d["capability"],
            issued_at=d["issued_at"],
            expires_at=d["expires_at"],
            nonce=d["nonce"],
            signature=d["signature"],
        )


def issue_token(
    identity: AgentIdentity,
    subject: str,
    capability: str,
    ttl_seconds: float,
) -> CapabilityToken:
    """Issue a capability token granting ``subject`` the named ``capability``,
    valid for ``ttl_seconds``, signed by ``identity``."""
    now = time.time()
    payload = {
        "issuer": identity.agent_id,
        "subject": subject,
        "capability": capability,
        "issued_at": now,
        "expires_at": now + ttl_seconds,
        "nonce": base58.b58encode(_secrets.token_bytes(16)).decode("ascii"),
    }
    signature = identity.sign(canonical_bytes(payload))
    return CapabilityToken(**payload, signature=signature)


def verify_token(
    token: CapabilityToken,
    issuer_public_key_b58: str,
    *,
    subject: Optional[str] = None,
    capability: Optional[str] = None,
    now: Optional[float] = None,
) -> bool:
    """Verify a capability token.

    Checks expiry, optional subject/capability binding, and the issuer's
    signature. ``issuer_public_key_b58`` must be the key valid at the time the
    token was issued — resolve it via :class:`identity.registry.KeyRegistry`
    if the issuer may have rotated.
    """
    now = now if now is not None else time.time()
    if now >= token.expires_at:
        return False
    if subject is not None and token.subject != subject:
        return False
    if capability is not None and token.capability != capability:
        return False
    return verify(issuer_public_key_b58, token.signing_payload(), token.signature)
