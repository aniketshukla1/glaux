"""Shared test setup.

Isolate the on-disk Glaux home so the suite never touches the real ``~/.glaux``
(llm.json, mcp_servers.json, schedules.json, workspace.json). This must run before
``core.api`` is imported by any test module, which pytest guarantees by importing
conftest first. Individual tests may still override ``GLAUX_HOME`` (e.g. the CLI
tests use a per-test ``tmp_path``).
"""

from __future__ import annotations

import os
import tempfile

# setdefault: respect an explicitly-set GLAUX_HOME (e.g. in CI), otherwise sandbox.
os.environ.setdefault("GLAUX_HOME", tempfile.mkdtemp(prefix="glaux-test-home-"))
