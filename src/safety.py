"""Global kill switch and dry-run mode.

``SAFETY_MODE`` gates all skill and agent execution:

- ``live``    — normal execution.
- ``dry_run`` — run the LLM/reasoning, but skip side-effecting execution
                (sandbox runs are short-circuited and logged as "would run").
- ``halted``  — short-circuit everything; the kill switch.

The mode is read from the ``GLAUX_SAFETY_MODE`` env var, or set
programmatically via :func:`set_mode` (which takes precedence).
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional

_ENV_VAR = "GLAUX_SAFETY_MODE"


class SafetyMode(str, Enum):
    LIVE = "live"
    DRY_RUN = "dry_run"
    HALTED = "halted"


class ExecutionHalted(Exception):
    """Raised when execution is attempted while the kill switch is engaged."""


_override: Optional[SafetyMode] = None


def current_mode() -> SafetyMode:
    """The effective safety mode (programmatic override beats env var)."""
    if _override is not None:
        return _override
    raw = os.environ.get(_ENV_VAR, "live").strip().lower()
    try:
        return SafetyMode(raw)
    except ValueError:
        return SafetyMode.LIVE


def set_mode(mode: Optional[SafetyMode | str]) -> None:
    """Set (or clear, with ``None``) the programmatic mode override."""
    global _override
    _override = SafetyMode(mode) if mode is not None else None


def execution_allowed() -> bool:
    return current_mode() == SafetyMode.LIVE


def is_dry_run() -> bool:
    return current_mode() == SafetyMode.DRY_RUN


def is_halted() -> bool:
    return current_mode() == SafetyMode.HALTED
