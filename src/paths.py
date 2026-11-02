"""Where Glaux keeps its state, and the names it answered to before the rename.

Settings are ``GLAUX_*`` environment variables. Installs from before the rename
set ``ATHENA_*``; importing this module copies those onto the new names (an
explicit ``GLAUX_*`` wins), so old shells, unit files and .env files keep working.
"""

from __future__ import annotations

import os
from pathlib import Path


def adopt_legacy_env(environ=os.environ) -> None:
    """Copy each pre-rename ``ATHENA_<X>`` onto ``GLAUX_<X>`` unless that is already set."""
    for key, value in list(environ.items()):
        if key.startswith("ATHENA_"):
            environ.setdefault("GLAUX_" + key[len("ATHENA_"):], value)


adopt_legacy_env()


def home() -> Path:
    """``GLAUX_HOME``, else ``~/.glaux``, or ``~/.athena`` when an install from before the rename lives there."""
    if os.environ.get("GLAUX_HOME"):
        return Path(os.environ["GLAUX_HOME"])
    new, old = Path.home() / ".glaux", Path.home() / ".athena"
    return old if old.is_dir() and not new.exists() else new
