"""The ``athena`` command line — install once, then drive the swarm from anywhere.

  athena up        start the server (serves the UI + API) as a background daemon
  athena down      stop the daemon
  athena status    is it running? which model, safety, how many signed blocks
  athena run "..." dispatch a directive and print the result
  athena serve     run in the foreground (Ctrl-C to stop)
  athena open      open the dashboard in a browser

Stdlib-only so ``athena --help`` / ``status`` / ``run`` work without importing
the heavy backend; ``up``/``serve`` shell out to uvicorn.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


# --- paths / pid ----------------------------------------------------------

def home_dir() -> Path:
    return Path(os.environ.get("ATHENA_HOME", Path.home() / ".athena"))


def pid_file() -> Path:
    return home_dir() / "athena.pid"


def log_file() -> Path:
    return home_dir() / "athena.log"


def write_pid(pid: int) -> None:
    home_dir().mkdir(parents=True, exist_ok=True)
    pid_file().write_text(str(pid))


def read_pid() -> int | None:
    try:
        return int(pid_file().read_text().strip())
    except (OSError, ValueError):
        return None


def process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


# --- http helpers (stdlib) ------------------------------------------------

def _get_json(url: str, timeout: float = 3.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post_json(url: str, payload: dict, timeout: float = 600.0) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# --- server spawning ------------------------------------------------------

def _uvicorn_cmd(host: str, port: int) -> list[str]:
    return [sys.executable, "-m", "uvicorn", "core.api:app", "--host", host, "--port", str(port)]


def _env_with_src() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _wait_healthy(base_url: str, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if _get_json(f"{base_url}/api/health").get("status") == "ok":
                return True
        except Exception:  # noqa: BLE001 - not up yet
            pass
        time.sleep(0.4)
    return False


# --- commands -------------------------------------------------------------

def cmd_up(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    existing = read_pid()
    if process_alive(existing):
        print(f"Athena is already running (pid {existing}) at {base_url}")
        return 0

    cmd = _uvicorn_cmd(args.host, args.port)
    if args.foreground:
        print(f"Serving Athena at {base_url}  (Ctrl-C to stop)")
        import subprocess

        return subprocess.call(cmd, env=_env_with_src())

    import subprocess

    home_dir().mkdir(parents=True, exist_ok=True)
    logf = open(log_file(), "a")
    proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True, env=_env_with_src())
    write_pid(proc.pid)
    if _wait_healthy(base_url):
        print(f"Athena is up at {base_url}  (pid {proc.pid}, logs: {log_file()})")
        if args.open:
            import webbrowser

            webbrowser.open(base_url)
        return 0
    print(f"Started (pid {proc.pid}) but it didn't become healthy — check {log_file()}", file=sys.stderr)
    return 1


def cmd_down(_args) -> int:
    pid = read_pid()
    if not process_alive(pid):
        print("Athena is not running.")
        pid_file().unlink(missing_ok=True)
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print(f"Could not stop pid {pid}: {e}", file=sys.stderr)
        return 1
    for _ in range(20):
        if not process_alive(pid):
            break
        time.sleep(0.2)
    pid_file().unlink(missing_ok=True)
    print(f"Stopped Athena (pid {pid}).")
    return 0


def cmd_status(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    pid = read_pid()
    if not process_alive(pid):
        print("Athena is not running.  Start it with:  athena up")
        return 1
    try:
        h = _get_json(f"{base_url}/api/health")
    except Exception as e:  # noqa: BLE001
        print(f"Running (pid {pid}) but the API didn't respond at {base_url}: {e}", file=sys.stderr)
        return 1
    print(f"Athena is up at {base_url}  (pid {pid})")
    print(f"  model:    {h.get('llm')}  ({h.get('backend')})")
    print(f"  safety:   {h.get('safety')}   approval: {h.get('approval')}")
    print(f"  ledger:   {h.get('blocks')} signed blocks")
    return 0


def _format_run_result(payload: dict) -> str:
    lines = []
    ok = payload.get("success")
    lines.append(("✓ " if ok else "✗ ") + (payload.get("final") or "(no result)"))
    verification = payload.get("verification") or {}
    cost = payload.get("cost") or {}
    bits = []
    if verification:
        bits.append("chain verified" if verification.get("valid") else "CHAIN INVALID")
    if cost.get("llm_calls") is not None:
        bits.append(f"{cost.get('llm_calls')} model calls")
    if cost.get("total_tokens"):
        bits.append(f"{cost.get('total_tokens')} tokens")
    if cost.get("usd"):
        bits.append(f"${cost.get('usd'):.4f}")
    if payload.get("new_blocks"):
        bits.append(f"{len(payload['new_blocks'])} blocks")
    if bits:
        lines.append("  " + " · ".join(bits))
    return "\n".join(lines)


def cmd_run(args) -> int:
    base_url = args.url or f"http://{args.host}:{args.port}"
    directive = " ".join(args.directive).strip()
    if not directive:
        print("Give a directive, e.g.  athena run \"summarize the news\"", file=sys.stderr)
        return 2
    try:
        payload = _post_json(f"{base_url}/api/task", {"directive": directive})
    except urllib.error.URLError:
        print(f"Couldn't reach Athena at {base_url}.  Start it with:  athena up", file=sys.stderr)
        return 1
    print(_format_run_result(payload))
    return 0 if payload.get("success") else 1


def cmd_open(args) -> int:
    import webbrowser

    base_url = f"http://{args.host}:{args.port}"
    webbrowser.open(base_url)
    print(f"Opening {base_url}")
    return 0


def _repo_root() -> Path:
    return SRC_DIR.parent


def cmd_desktop(args) -> int:
    import subprocess

    src_tauri = _repo_root() / "desktop" / "src-tauri"
    if not src_tauri.is_dir():
        print(f"Desktop app not found (expected {src_tauri}).", file=sys.stderr)
        return 1
    mode = "build" if args.build else "dev"
    print(f"Launching the Athena desktop app  (cargo tauri {mode})…")
    try:
        return subprocess.call(["cargo", "tauri", mode], cwd=str(src_tauri))
    except FileNotFoundError:
        print("cargo not found — install Rust + `cargo install tauri-cli` to build the desktop app.", file=sys.stderr)
        return 1


def cmd_version(_args) -> int:
    print("athena 0.1")
    return 0


# --- parser ---------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="athena", description="Athena — self-improving multi-agent swarm.")
    p.add_argument("--host", default=DEFAULT_HOST, help=f"server host (default {DEFAULT_HOST})")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"server port (default {DEFAULT_PORT})")
    sub = p.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="start the server as a background daemon")
    up.add_argument("--foreground", "-f", action="store_true", help="run in the foreground")
    up.add_argument("--open", action="store_true", help="open the dashboard once it's up")
    up.set_defaults(func=cmd_up)

    sub.add_parser("down", help="stop the daemon").set_defaults(func=cmd_down)
    sub.add_parser("status", help="show whether Athena is running").set_defaults(func=cmd_status)
    sub.add_parser("serve", help="run in the foreground (alias for `up -f`)").set_defaults(
        func=lambda a: cmd_up(argparse.Namespace(**{**vars(a), "foreground": True, "open": False}))
    )
    sub.add_parser("open", help="open the dashboard in a browser").set_defaults(func=cmd_open)
    sub.add_parser("version", help="print the version").set_defaults(func=cmd_version)

    desktop = sub.add_parser("desktop", help="launch the native desktop app")
    desktop.add_argument("--build", action="store_true", help="build a distributable .app instead of running")
    desktop.set_defaults(func=cmd_desktop)

    run = sub.add_parser("run", help="dispatch a directive to the running server")
    run.add_argument("directive", nargs="+", help="what the swarm should do")
    run.add_argument("--url", help="base URL of a running server (overrides --host/--port)")
    run.set_defaults(func=cmd_run)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
