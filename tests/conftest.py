"""Shared test setup.

Isolate the on-disk Athena home so the suite never touches the real ``~/.athena``
(llm.json, mcp_servers.json, schedules.json, workspace.json). This must run before
``core.api`` is imported by any test module, which pytest guarantees by importing
conftest first. Individual tests may still override ``ATHENA_HOME`` (e.g. the CLI
tests use a per-test ``tmp_path``).
"""

from __future__ import annotations

import os
import tempfile

# setdefault: respect an explicitly-set ATHENA_HOME (e.g. in CI), otherwise sandbox.
os.environ.setdefault("ATHENA_HOME", tempfile.mkdtemp(prefix="athena-test-home-"))
