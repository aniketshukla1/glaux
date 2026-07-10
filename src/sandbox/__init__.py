"""Athena skill sandbox: isolated execution of LLM-generated code.

Public API:
- :func:`run` — execute code under declared :class:`Capabilities`
- :class:`Capabilities`, :class:`SandboxResult`
- :class:`SecretsBroker`, :class:`DictSecretsBackend`, :class:`EnvSecretsBackend`
- :class:`WasmSandbox` — the v2 zero-ambient-authority backend (opt-in)
"""

from .capabilities import Capabilities, SandboxResult
from .runner import run
from .secrets import DictSecretsBackend, EnvSecretsBackend, SecretsBroker
from .wasm import WasmSandbox

__all__ = [
    "run",
    "Capabilities",
    "SandboxResult",
    "SecretsBroker",
    "DictSecretsBackend",
    "EnvSecretsBackend",
    "WasmSandbox",
]
