"""In-sandbox execution harness (stdlib only, no Glaux imports).

Runs in the isolated child process. Reads a job file describing the skill
code, entrypoint, inputs, and capability guards; installs Python-level guards
(network + filesystem); executes the code; and writes a result file.

This is *defense in depth*, not a hard security boundary on its own — it is
combined with process isolation, a minimal environment, resource limits, and
a parent-side memory/timeout watcher. The v2 backend (``wasm.py``, opt-in via
``GLAUX_SANDBOX_BACKEND``) replaces this with a WASM runtime that has no
syscalls by default; see ``WASM_V2.md``.
"""

from __future__ import annotations

import builtins
import io
import json
import os
import resource
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout


def install_net_guard() -> None:
    import socket

    def _blocked(*_a, **_k):
        raise PermissionError("network access not permitted by skill capabilities")

    socket.socket = _blocked  # type: ignore[assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]
    if hasattr(socket, "create_server"):
        socket.create_server = _blocked  # type: ignore[assignment]


def install_proc_guard() -> None:
    """Block process creation at runtime — os.system/popen/exec*/spawn*/fork and
    subprocess. The static capability check already rejects these, but this closes
    dynamic bypasses (e.g. getattr(__import__('o'+'s'), 'system'))."""

    def _blocked(*_a, **_k):
        raise PermissionError("spawning processes is not permitted in a skill sandbox")

    for name in ("system", "popen", "posix_spawn", "posix_spawnp", "fork", "forkpty"):
        if hasattr(os, name):
            setattr(os, name, _blocked)
    for name in [n for n in dir(os) if n.startswith("exec") or n.startswith("spawn")]:
        setattr(os, name, _blocked)
    try:
        import subprocess

        for name in ("run", "call", "check_call", "check_output", "Popen", "getoutput", "getstatusoutput"):
            if hasattr(subprocess, name):
                setattr(subprocess, name, _blocked)
    except Exception:  # noqa: BLE001
        pass


def install_fs_guard(fs_read, fs_write, scratch: str) -> None:
    real_open = builtins.open
    real_os_open = os.open
    read_roots = [os.path.realpath(p) for p in fs_read] + [
        scratch,
        os.path.realpath(sys.base_prefix),
        os.path.realpath(sys.prefix),
    ]
    write_roots = [os.path.realpath(p) for p in fs_write] + [scratch]

    def _under(path: str, roots) -> bool:
        rp = os.path.realpath(path)
        return any(rp == r or rp.startswith(r + os.sep) for r in roots)

    def _strpath(p) -> str:
        p = os.fspath(p)
        return p.decode() if isinstance(p, bytes) else p

    def guarded_open(file, mode="r", *args, **kwargs):
        writing = any(c in mode for c in ("w", "a", "x", "+"))
        if isinstance(file, (str, bytes, os.PathLike)):
            p = _strpath(file)
            if writing and not _under(p, write_roots):
                raise PermissionError(f"write to {p!r} not permitted by skill capabilities")
            if not writing and not _under(p, read_roots):
                raise PermissionError(f"read of {p!r} not permitted by skill capabilities")
        return real_open(file, mode, *args, **kwargs)

    # low-level os.open — the bypass around builtins.open
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

    def guarded_os_open(path, flags, *args, **kwargs):
        p = _strpath(path)
        if (flags & write_flags) and not _under(p, write_roots):
            raise PermissionError(f"write to {p!r} not permitted by skill capabilities")
        if not (flags & write_flags) and not _under(p, read_roots):
            raise PermissionError(f"read of {p!r} not permitted by skill capabilities")
        return real_os_open(path, flags, *args, **kwargs)

    # destructive single-path ops (remove/unlink/rmdir) need write access
    def _guard_one(fn):
        def wrapped(path, *a, **k):
            if not _under(_strpath(path), write_roots):
                raise PermissionError(f"modifying {_strpath(path)!r} not permitted by skill capabilities")
            return fn(path, *a, **k)
        return wrapped

    def _guard_two(fn):
        def wrapped(src, dst, *a, **k):
            for x in (src, dst):
                if not _under(_strpath(x), write_roots):
                    raise PermissionError(f"modifying {_strpath(x)!r} not permitted by skill capabilities")
            return fn(src, dst, *a, **k)
        return wrapped

    builtins.open = guarded_open  # type: ignore[assignment]
    os.open = guarded_os_open  # type: ignore[assignment]
    for name in ("remove", "unlink", "rmdir", "mkdir", "makedirs"):
        if hasattr(os, name):
            setattr(os, name, _guard_one(getattr(os, name)))
    for name in ("rename", "replace", "link", "symlink"):
        if hasattr(os, name):
            setattr(os, name, _guard_two(getattr(os, name)))


def main() -> None:
    jobfile, resultfile = sys.argv[1], sys.argv[2]
    with open(jobfile) as f:
        job = json.load(f)

    code = job["code"]
    entrypoint = job.get("entrypoint")
    inputs = job.get("inputs") or {}
    caps = job.get("caps") or {}
    scratch = os.path.realpath(job.get("scratch") or os.getcwd())

    if not caps.get("net", False):
        install_net_guard()
    install_proc_guard()  # skills never spawn processes — that's the agent's job
    install_fs_guard(caps.get("fs_read") or [], caps.get("fs_write") or [], scratch)

    out_buf, err_buf = io.StringIO(), io.StringIO()
    result = {
        "ok": False,
        "return_value": None,
        "return_repr": False,
        "stdout": "",
        "stderr": "",
        "error": None,
        "traceback": None,
        "platform": sys.platform,
    }
    namespace: dict = {"__name__": "__skill__"}
    try:
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            exec(compile(code, "<skill>", "exec"), namespace)
            rv = None
            if entrypoint:
                fn = namespace.get(entrypoint)
                if not callable(fn):
                    raise NameError(f"entrypoint {entrypoint!r} is not defined")
                rv = fn(**inputs)
        try:
            json.dumps(rv)
            result["return_value"] = rv
        except (TypeError, ValueError):
            result["return_value"] = repr(rv)
            result["return_repr"] = True
        result["ok"] = True
    except BaseException as e:  # noqa: BLE001 - report everything to the parent
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()
    finally:
        result["stdout"] = out_buf.getvalue()
        result["stderr"] = err_buf.getvalue()
        result["peak_rss"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        with open(resultfile, "w") as f:
            json.dump(result, f)


if __name__ == "__main__":
    main()
