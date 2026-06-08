"""Secrets broker.

Skills never receive raw credentials as arguments. Instead they *declare*
which named secrets they need (via :class:`Capabilities`), and the broker
resolves those names to values that the runner injects as scoped env vars at
sandbox launch — and only those. Resolved values are also redacted from
captured output before they re-enter the reasoning window or the ledger.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional, Protocol


class SecretsBackend(Protocol):
    def get(self, name: str) -> Optional[str]: ...


class DictSecretsBackend:
    """In-memory backend, primarily for tests and local development."""

    def __init__(self, mapping: Mapping[str, str]) -> None:
        self._mapping = dict(mapping)

    def get(self, name: str) -> Optional[str]:
        return self._mapping.get(name)


class EnvSecretsBackend:
    """Resolves ``name`` from ``<prefix><NAME>`` environment variables."""

    def __init__(self, prefix: str = "ATHENA_SECRET_") -> None:
        self._prefix = prefix

    def get(self, name: str) -> Optional[str]:
        return os.environ.get(self._prefix + name.upper())


class SecretsBroker:
    def __init__(self, backend: SecretsBackend) -> None:
        self._backend = backend

    def resolve(self, name: str) -> str:
        value = self._backend.get(name)
        if value is None:
            raise KeyError(f"unknown secret: {name!r}")
        return value

    def resolve_all(self, names: list[str]) -> dict[str, str]:
        return {name: self.resolve(name) for name in names}
