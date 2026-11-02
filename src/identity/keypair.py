"""Ed25519 agent identity, signing, and key rotation.

An agent's identity is an Ed25519 keypair. The ``agent_id`` is the base58
encoding of the *genesis* public key and is stable for the lifetime of the
agent — even across key rotations. Rotation introduces a new signing key
authorized by a record signed with the *previous* key, forming a chain of
trust verifiable from genesis (see :mod:`identity.registry`).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import base58
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from paths import home

from .canonical import canonical_bytes

DEFAULT_NAMESPACE = "default"
AGENT_HOME = home() / "agents"

_RAW_PUB = (serialization.Encoding.Raw, serialization.PublicFormat.Raw)
_RAW_PRIV = (
    serialization.Encoding.Raw,
    serialization.PrivateFormat.Raw,
    serialization.NoEncryption(),
)


def _pub_to_b58(pub: Ed25519PublicKey) -> str:
    return base58.b58encode(pub.public_bytes(*_RAW_PUB)).decode("ascii")


def _b58_to_pub(s: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(base58.b58decode(s))


def verify(public_key_b58: str, payload: bytes, signature_b58: str) -> bool:
    """Return True iff ``signature_b58`` is a valid signature of ``payload``
    by the holder of ``public_key_b58``. Never raises on bad input."""
    try:
        pub = _b58_to_pub(public_key_b58)
        pub.verify(base58.b58decode(signature_b58), payload)
        return True
    except (InvalidSignature, ValueError):
        return False


@dataclass(frozen=True)
class RotationRecord:
    """A signed authorization to move signing authority old_key -> new_key.

    Signed by the *old* key, so a verifier holding the prior key can confirm
    the rotation was authorized by whoever controlled the agent before.
    """

    agent_id: str
    old_pubkey: str
    new_pubkey: str
    rotated_at: float
    signature: str  # base58, by the old key, over signing_payload()

    def signing_payload(self) -> bytes:
        return canonical_bytes(
            {
                "agent_id": self.agent_id,
                "old_pubkey": self.old_pubkey,
                "new_pubkey": self.new_pubkey,
                "rotated_at": self.rotated_at,
            }
        )

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "old_pubkey": self.old_pubkey,
            "new_pubkey": self.new_pubkey,
            "rotated_at": self.rotated_at,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RotationRecord":
        return cls(
            agent_id=d["agent_id"],
            old_pubkey=d["old_pubkey"],
            new_pubkey=d["new_pubkey"],
            rotated_at=d["rotated_at"],
            signature=d["signature"],
        )


class AgentIdentity:
    """An agent's cryptographic identity: a current signing key plus the
    rotation chain that links it back to the genesis key."""

    def __init__(
        self,
        signing_key: Ed25519PrivateKey,
        agent_id: str,
        namespace: str = DEFAULT_NAMESPACE,
        rotation_chain: Optional[list[RotationRecord]] = None,
    ) -> None:
        self._signing_key = signing_key
        self.agent_id = agent_id
        self.namespace = namespace
        self.rotation_chain: list[RotationRecord] = list(rotation_chain or [])

    @classmethod
    def generate(cls, namespace: str = DEFAULT_NAMESPACE) -> "AgentIdentity":
        sk = Ed25519PrivateKey.generate()
        agent_id = _pub_to_b58(sk.public_key())
        return cls(sk, agent_id, namespace)

    @property
    def public_key_b58(self) -> str:
        """The *current* signing public key (differs from agent_id after a rotation)."""
        return _pub_to_b58(self._signing_key.public_key())

    def sign(self, payload: bytes) -> str:
        """Sign ``payload`` with the current key; returns a base58 signature."""
        return base58.b58encode(self._signing_key.sign(payload)).decode("ascii")

    def signing_key_b58(self) -> str:
        """Base58 of the current 32-byte private key seed.

        Sensitive: intended for in-process trusted components (e.g. the ledger's
        native signing kernel) that already share this process's trust boundary.
        Standard Ed25519, so a signature produced from this seed in Rust verifies
        against :pyattr:`public_key_b58` here, and vice versa.
        """
        raw = self._signing_key.private_bytes(*_RAW_PRIV)
        return base58.b58encode(raw).decode("ascii")

    def rotate(self) -> RotationRecord:
        """Generate a new signing key, authorized by the current key.

        Returns the :class:`RotationRecord`. After this call the identity signs
        with the new key, but ``agent_id`` is unchanged.
        """
        old_pub = self.public_key_b58
        new_sk = Ed25519PrivateKey.generate()
        new_pub = _pub_to_b58(new_sk.public_key())
        rotated_at = time.time()
        unsigned = {
            "agent_id": self.agent_id,
            "old_pubkey": old_pub,
            "new_pubkey": new_pub,
            "rotated_at": rotated_at,
        }
        sig = base58.b58encode(
            self._signing_key.sign(canonical_bytes(unsigned))
        ).decode("ascii")
        record = RotationRecord(self.agent_id, old_pub, new_pub, rotated_at, sig)
        self._signing_key = new_sk
        self.rotation_chain.append(record)
        return record

    # --- persistence ---------------------------------------------------

    def save(self, directory: Optional[Path] = None) -> Path:
        """Persist the current private key + rotation chain to ``<agent_id>.key``
        with 0600 permissions."""
        directory = Path(directory) if directory else AGENT_HOME
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.agent_id}.key"
        priv_raw = self._signing_key.private_bytes(*_RAW_PRIV)
        blob = {
            "agent_id": self.agent_id,
            "namespace": self.namespace,
            "private_key": base58.b58encode(priv_raw).decode("ascii"),
            "rotation_chain": [r.to_dict() for r in self.rotation_chain],
        }
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(blob, f)
        os.chmod(path, 0o600)
        return path

    @classmethod
    def load(cls, agent_id: str, directory: Optional[Path] = None) -> "AgentIdentity":
        directory = Path(directory) if directory else AGENT_HOME
        path = directory / f"{agent_id}.key"
        with open(path) as f:
            blob = json.load(f)
        sk = Ed25519PrivateKey.from_private_bytes(base58.b58decode(blob["private_key"]))
        chain = [RotationRecord.from_dict(r) for r in blob.get("rotation_chain", [])]
        return cls(
            sk,
            blob["agent_id"],
            blob.get("namespace", DEFAULT_NAMESPACE),
            chain,
        )
