"""Skill sandbox runner.

Executes LLM-generated Python in an isolated child process — never in the
agent's own interpreter. Enforcement layers:

1. **Process isolation** — separate process, own session/process-group.
2. **Minimal environment** — the child sees only PATH, HOME(=scratch), and
   explicitly declared secrets. The parent's env (and any undeclared secret)
   is invisible.
3. **Resource limits** — RLIMIT_CPU and RLIMIT_NOFILE via ``preexec_fn``.
4. **Parent watchers** — wall-clock timeout and a polling RSS monitor that
   kill the whole process group on breach (reliable on macOS where RLIMIT_AS
   is not).
5. **In-sandbox guards** — network and filesystem guards (see ``_harness``).

Honors the global kill switch: ``halted`` refuses to run; ``dry_run`` returns
without executing.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import safety

from .capabilities import Capabilities, SandboxResult
from .secrets import SecretsBroker

_HARNESS = str(Path(__file__).parent / "_harness.py")
_RSS_POLL_S = 0.05


def _killpg(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def _preexec(caps: Capabilities):
    def fn() -> None:
        os.setsid()  # own process group so we can kill all descendants
        try:
            cpu = int(caps.time_limit_s) + 1
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        except Exception:
            pass
        try:
            import resource

            resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        except Exception:
            pass
        try:
            import resource

            fsize = 64 * 1024 * 1024  # cap any single file write at 64 MB (no disk-fill)
            resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        except Exception:
            pass
        try:
            import resource

            # best-effort: shrink the process-count ceiling to blunt fork bombs
            soft, hard = resource.getrlimit(resource.RLIMIT_NPROC)
            if soft == resource.RLIM_INFINITY or soft > 512:
                resource.setrlimit(resource.RLIMIT_NPROC, (512, hard))
        except Exception:
            pass

    return fn


def _rss_mb(pid: int) -> Optional[float]:
    try:
        out = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(pid)],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out:
            return int(out) / 1024.0  # ps reports KB
    except Exception:
        return None
    return None


def _mem_watch(proc, limit_mb, killed: dict, peak: list) -> None:
    while proc.poll() is None:
        rss = _rss_mb(proc.pid)
        if rss is not None:
            peak[0] = max(peak[0], rss)
            if limit_mb and rss > limit_mb:
                killed["reason"] = "memory"
                _killpg(proc)
                return
        time.sleep(_RSS_POLL_S)


def _normalize_rss(raw, platform: str) -> float:
    if not raw:
        return 0.0
    # macOS reports ru_maxrss in bytes; Linux in kilobytes.
    return (raw / 1_048_576.0) if platform == "darwin" else (raw / 1024.0)


def _redact(text: Optional[str], secret_values: list[str]) -> Optional[str]:
    if not text:
        return text
    for s in secret_values:
        if s:
            text = text.replace(s, "***REDACTED***")
    return text


def run(
    code: str,
    caps: Optional[Capabilities] = None,
    inputs: Optional[dict] = None,
    entrypoint: Optional[str] = None,
    broker: Optional[SecretsBroker] = None,
) -> SandboxResult:
    """Execute ``code`` in the sandbox under ``caps``.

    If ``entrypoint`` is given, the named function is called with ``**inputs``
    and its (JSON-serializable) return value is captured.
    """
    caps = caps or Capabilities()
    inputs = inputs or {}

    mode = safety.current_mode()
    if mode == safety.SafetyMode.HALTED:
        return SandboxResult(
            ok=False,
            error="execution halted by kill switch",
            killed_reason="halted",
        )
    if mode == safety.SafetyMode.DRY_RUN:
        return SandboxResult(
            ok=True,
            stdout="[dry-run] sandbox execution skipped",
            return_value=None,
        )

    # Backend selection. Default is the subprocess sandbox below. The WASM v2
    # backend (no ambient authority) is opt-in and, when it can't run Python
    # skills yet, "auto" transparently falls back here.
    backend = os.environ.get("ATHENA_SANDBOX_BACKEND", "subprocess").lower()
    if backend in ("wasm", "auto"):
        from .wasm import WasmSandbox

        if WasmSandbox.python_available():
            return WasmSandbox().run(code, caps=caps, inputs=inputs, entrypoint=entrypoint)
        if backend == "wasm":
            return SandboxResult(
                ok=False,
                error="ATHENA_SANDBOX_BACKEND=wasm but no CPython-WASI runtime "
                "configured (set ATHENA_PYTHON_WASM); refusing to silently run "
                "with weaker isolation",
            )
        # backend == "auto": fall through to the subprocess sandbox

    # Resolve declared secrets (parent-side) for injection + redaction.
    secret_values: list[str] = []
    injected: dict[str, str] = {}
    if caps.secrets:
        if broker is None:
            return SandboxResult(
                ok=False, error="secrets requested but no SecretsBroker provided"
            )
        try:
            injected = broker.resolve_all(caps.secrets)
        except KeyError as e:
            return SandboxResult(ok=False, error=str(e))
        secret_values = list(injected.values())

    with tempfile.TemporaryDirectory(prefix="athena-skill-") as scratch:
        jobfile = os.path.join(scratch, "job.json")
        resultfile = os.path.join(scratch, "result.json")
        with open(jobfile, "w") as f:
            json.dump(
                {
                    "code": code,
                    "entrypoint": entrypoint,
                    "inputs": inputs,
                    "caps": caps.to_job(),
                    "scratch": scratch,
                },
                f,
            )

        # Minimal environment: no inheritance of the parent's secrets/config.
        child_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": scratch,
            "ATHENA_SANDBOX": "1",
        }
        child_env.update(injected)

        killed: dict = {"reason": None}
        peak: list = [0.0]
        start = time.monotonic()
        proc = subprocess.Popen(
            [sys.executable, _HARNESS, jobfile, resultfile],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=scratch,
            env=child_env,
            preexec_fn=_preexec(caps),
            text=True,
        )
        watcher = threading.Thread(
            target=_mem_watch, args=(proc, caps.mem_mb, killed, peak), daemon=True
        )
        watcher.start()

        harness_err = ""
        try:
            _, harness_err = proc.communicate(timeout=caps.time_limit_s)
        except subprocess.TimeoutExpired:
            killed["reason"] = killed["reason"] or "timeout"
            _killpg(proc)
            try:
                _, harness_err = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        duration = time.monotonic() - start
        watcher.join(timeout=0.5)

        # Read the child's result file, if it managed to write one.
        payload: Optional[dict] = None
        try:
            with open(resultfile) as f:
                payload = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            payload = None

    if killed["reason"]:
        return SandboxResult(
            ok=False,
            error=f"execution killed: {killed['reason']}",
            killed_reason=killed["reason"],
            exit_code=proc.returncode,
            duration_s=duration,
            peak_rss_mb=peak[0],
        )

    if payload is None:
        return SandboxResult(
            ok=False,
            error="sandbox produced no result (process crashed)",
            stderr=_redact(harness_err, secret_values) or "",
            exit_code=proc.returncode,
            duration_s=duration,
            peak_rss_mb=peak[0],
        )

    return_value = payload.get("return_value")
    if payload.get("return_repr") and isinstance(return_value, str):
        return_value = _redact(return_value, secret_values)

    return SandboxResult(
        ok=bool(payload.get("ok")),
        return_value=return_value,
        stdout=_redact(payload.get("stdout", ""), secret_values) or "",
        stderr=_redact(payload.get("stderr", ""), secret_values) or "",
        error=_redact(payload.get("error"), secret_values),
        traceback=_redact(payload.get("traceback"), secret_values),
        exit_code=proc.returncode,
        duration_s=duration,
        peak_rss_mb=_normalize_rss(payload.get("peak_rss"), payload.get("platform", ""))
        or peak[0],
    )
