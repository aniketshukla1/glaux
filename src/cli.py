"""The ``athena`` command line — install once, then drive the swarm from anywhere.

Server:
  athena up        start the server (serves the UI + API) as a background daemon
  athena down      ·  restart  ·  rebuild  (rebuild the UI, then restart)
  athena status    is it running? which model, safety, how many signed blocks
  athena serve     run in the foreground   ·   athena open   open the dashboard

Drive the agent:
  athena run "..." dispatch a directive — streams the run live (--json for scripts)
  athena chat      interactive terminal chat (one conversation, Ctrl-C stops a run)
  athena search    search the web via the agent's tools
  athena remember  store a fact   ·   athena memory <layer> [query]   browse it

Inspect:
  athena sessions · agents · skills · recipes · personas · metrics · verify · eval
  athena models [--set ollama:qwen2.5:7b-instruct]   show / switch the LLM

Configure (parity with the app's Settings):
  athena safety [live|dry-run|halted]   ·   athena approval [auto|gated]
  athena workspace [on|off]             jailed file tools (edit_file, glob, grep…)
  athena playbooks [list|add|rm|on|off] ·   athena subagents [list|add|rm]
  athena skills [synth "…"|approve <id>|reject <id>]   synthesize / gate skills
  athena evolution [status|evolve|revert|auto on|unpin <id>|unretire <role>]
  athena personas [list|add|rm]         ·   athena recipes [list|add|rm]
  athena cache [status|on|off|clear]    semantic answer cache (skip repeat runs)

Account / admin:
  athena login · logout · whoami   ·   athena messaging   (gateways, admin)

Stdlib-only so ``athena --help`` / ``status`` / ``run`` work without importing
the heavy backend; ``up``/``serve`` shell out to uvicorn. Live runs stream over
Server-Sent Events, rendered with nothing but urllib.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import time
import urllib.error
import urllib.parse
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


# --- auth token (CLI session) ---------------------------------------------

def token_file() -> Path:
    return home_dir() / "cli_token"


def read_token() -> str | None:
    try:
        return token_file().read_text().strip() or None
    except OSError:
        return None


def write_token(token: str | None) -> None:
    home_dir().mkdir(parents=True, exist_ok=True)
    if token:
        token_file().write_text(token)
        try:
            os.chmod(token_file(), 0o600)
        except OSError:
            pass
    else:
        token_file().unlink(missing_ok=True)


def _auth_headers() -> dict:
    tok = read_token()
    return {"Authorization": f"Bearer {tok}"} if tok else {}


# --- http helpers (stdlib) ------------------------------------------------

def _detail(e: urllib.error.HTTPError) -> str:
    try:
        return json.loads(e.read().decode()).get("detail") or f"HTTP {e.code}"
    except Exception:  # noqa: BLE001
        return f"HTTP {e.code}"


def _get_json(url: str, timeout: float = 3.0) -> dict:
    req = urllib.request.Request(url, headers=_auth_headers())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post_json(url: str, payload: dict, timeout: float = 600.0) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **_auth_headers()}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _req_json(method: str, url: str, payload: dict | None = None, timeout: float = 600.0) -> dict:
    """A JSON request for any method (POST/PATCH/DELETE). DELETE sends no body."""
    data = json.dumps(payload).encode() if (payload is not None and method in ("POST", "PATCH", "PUT")) else None
    headers = dict(_auth_headers())
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
        return json.loads(body) if body else {}


# --- terminal output (stdlib ANSI; respects NO_COLOR and non-TTY) ---------

_STYLES = {
    "dim": "2", "bold": "1", "red": "31", "green": "32", "yellow": "33",
    "blue": "34", "magenta": "35", "cyan": "36", "gray": "90",
}


def _use_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"


def style(text: str, *names: str) -> str:
    if not names or not _use_color():
        return text
    codes = ";".join(_STYLES[n] for n in names if n in _STYLES)
    return f"\033[{codes}m{text}\033[0m" if codes else text


def _err(msg: str) -> int:
    print(style(msg, "red"), file=sys.stderr)
    return 1


def _api(base_url: str, method: str, path: str, payload: dict | None = None):
    """Call a JSON endpoint; on failure print a friendly message and return None."""
    url = f"{base_url}{path}"
    try:
        if method == "GET":
            return _get_json(url)
        return _req_json(method, url, payload)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            _err("Not signed in. Run:  athena login")
        elif e.code == 403:
            _err("Admin sign-in required for this.")
        else:
            _err(_detail(e))
        return None
    except urllib.error.URLError:
        _err(f"Couldn't reach Athena at {base_url}.  Start it with:  athena up")
        return None


# how the swarm's signed ledger actions read as live status lines
ACTION_VERB = {
    "PLAN": "planning the team",
    "CALL_AGENT": "delegating",
    "CAPABILITY_GRANT": "granting capability",
    "THINK": "thinking",
    "EMIT_OBSERVATION": "observed",
    "REFLECT": "verifying",
    "MCP_TOOL": "using a tool",
    "CALL_SKILL": "running a skill",
    "SYNTHESIZE_SKILL": "learning a skill",
}


# --- streaming a task over SSE (stdlib urllib) ----------------------------

def _open_stream(base_url: str, payload: dict, timeout: float = 900.0):
    req = urllib.request.Request(
        f"{base_url}/api/task/stream", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream", **_auth_headers()},
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _iter_sse(resp):
    for raw in resp:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        if line.startswith("data:"):
            data = line[5:].strip()
            if data:
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    continue


def _print_summary(result: dict) -> None:
    cost = result.get("cost") or {}
    ver = result.get("verification") or {}
    bits = []
    if ver:
        bits.append(style("✓ chain verified", "green") if ver.get("valid") else style("✗ chain invalid", "red"))
    if result.get("model"):
        bits.append(result["model"])
    if cost.get("llm_calls") is not None:
        bits.append(f"{cost['llm_calls']} calls")
    if cost.get("total_tokens"):
        bits.append(f"{cost['total_tokens']:,} tokens")
    if cost.get("usd"):
        bits.append(f"${cost['usd']:.4f}")
    if bits:
        print(style("  " + " · ".join(bits), "dim"))
    sources = result.get("sources") or []
    if sources:
        print(style(f"  sources ({len(sources)})", "dim"))
        for i, s in enumerate(sources[:8], 1):
            title = s.get("title") or s.get("url")
            print("    " + style(f"{i}.", "gray") + f" {title}  " + style(s.get("url", ""), "gray"))


def _render_stream(base_url: str, directive: str, session_id: str | None = None) -> dict | None:
    """Stream a task and render the multi-agent run live. Returns the result dict
    (for the exit code), or None on a transport/auth error."""
    role_of = {}
    try:
        for a in _get_json(f"{base_url}/api/agents").get("agents", []):
            role_of[a["agent_id"]] = a["role"]
    except Exception:  # noqa: BLE001
        pass
    try:
        resp = _open_stream(base_url, {"directive": directive, "session_id": session_id})
    except urllib.error.HTTPError as e:
        if e.code == 401:
            _err("Not signed in. Run:  athena login")
        else:
            _err(_detail(e))
        return None
    except urllib.error.URLError:
        _err(f"Couldn't reach Athena at {base_url}.  Start it with:  athena up")
        return None

    result = None
    answering = False
    try:
        with resp:
            for ev in _iter_sse(resp):
                t = ev.get("type")
                if t == "block" and not answering:
                    b = ev.get("block", {})
                    role = role_of.get(b.get("agent_id"), "agent")
                    verb = ACTION_VERB.get(b.get("action_type"), (b.get("action_type") or "").replace("_", " ").lower())
                    print(style(f"  ◆ {role:<11}", "cyan") + style(verb, "gray"))
                elif t == "token":
                    if not answering:
                        answering = True
                        print(style("\n  ⬡ answer", "green"))
                        sys.stdout.write("  ")
                    text = ev.get("text", "")
                    sys.stdout.write(text.replace("\n", "\n  "))
                    sys.stdout.flush()
                elif t == "done":
                    result = ev.get("result")
                elif t == "error":
                    print()
                    _err("✗ " + (ev.get("detail") or "the run failed"))
    except KeyboardInterrupt:
        try:
            _post_json(f"{base_url}/api/task/stop", {}, timeout=5)
        except Exception:  # noqa: BLE001
            pass
        print(style("\n  ⊘ stopping…", "yellow"))
        return None
    if answering:
        print()
    elif result and result.get("final"):  # answer wasn't streamed (short/non-stream synthesis)
        print(style("\n  ⬡ answer", "green"))
        print("  " + (result["final"] or "").replace("\n", "\n  "))
    if result:
        _print_summary(result)
    return result


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


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def _wait_port_free(host: str, port: int, timeout: float = 15.0) -> bool:
    """Block until nothing is listening on the port — the missing step that made
    a quick down+up race (the new server fails to bind to a port the old one
    hasn't released yet)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _port_in_use(host, port):
            return True
        time.sleep(0.3)
    return not _port_in_use(host, port)


def _stop_daemon() -> int | None:
    """Stop the daemon and wait for the process to be gone, escalating SIGTERM ->
    SIGKILL if it doesn't exit. Returns the pid it stopped, or None if nothing ran."""
    pid = read_pid()
    if not process_alive(pid):
        pid_file().unlink(missing_ok=True)
        return None
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    for _ in range(40):  # up to ~8s for a graceful shutdown
        if not process_alive(pid):
            break
        time.sleep(0.2)
    if process_alive(pid):  # didn't go quietly — force it
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        for _ in range(15):
            if not process_alive(pid):
                break
            time.sleep(0.2)
    pid_file().unlink(missing_ok=True)
    return pid


def _start_daemon(host: str, port: int, *, open_browser: bool = False) -> int:
    """Spawn the uvicorn daemon, record its pid, and wait until it's healthy."""
    import subprocess

    base_url = f"http://{host}:{port}"
    home_dir().mkdir(parents=True, exist_ok=True)
    logf = open(log_file(), "a")
    proc = subprocess.Popen(
        _uvicorn_cmd(host, port), stdout=logf, stderr=subprocess.STDOUT,
        start_new_session=True, env=_env_with_src(),
    )
    write_pid(proc.pid)
    if _wait_healthy(base_url):
        print(f"Athena is up at {base_url}  (pid {proc.pid}, logs: {log_file()})")
        if open_browser:
            import webbrowser

            webbrowser.open(base_url)
        return 0
    print(f"Started (pid {proc.pid}) but it didn't become healthy — check {log_file()}", file=sys.stderr)
    return 1


def _build_frontend() -> int:
    """Build the React frontend so the daemon serves the latest UI."""
    import subprocess

    frontend = _repo_root() / "frontend"
    if not (frontend / "package.json").is_file():
        print(f"No frontend at {frontend} — skipping build.")
        return 0
    print("Building the frontend (npm run build)…")
    try:
        rc = subprocess.call(["npm", "run", "build"], cwd=str(frontend))
    except FileNotFoundError:
        print("npm not found — install Node.js to build the frontend.", file=sys.stderr)
        return 1
    if rc != 0:
        print("Frontend build failed — leaving the running server untouched.", file=sys.stderr)
    return rc


# --- commands -------------------------------------------------------------

def cmd_up(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    existing = read_pid()
    if process_alive(existing):
        print(f"Athena is already running (pid {existing}) at {base_url}")
        return 0

    if args.foreground:
        print(f"Serving Athena at {base_url}  (Ctrl-C to stop)")
        import subprocess

        return subprocess.call(_uvicorn_cmd(args.host, args.port), env=_env_with_src())

    return _start_daemon(args.host, args.port, open_browser=args.open)


def cmd_restart(args) -> int:
    """Cleanly stop, wait for the port to free, then start — so a restart can never
    silently no-op against a port the old process hasn't released yet."""
    pid = _stop_daemon()
    print("Stopped the running daemon." if pid else "No daemon was running.")
    if not _wait_port_free(args.host, args.port):
        print(
            f"Port {args.port} is still in use by something else — free it and retry.",
            file=sys.stderr,
        )
        return 1
    return _start_daemon(args.host, args.port, open_browser=getattr(args, "open", False))


def cmd_rebuild(args) -> int:
    """Rebuild the frontend, then clean-restart so the daemon serves the fresh UI."""
    if not args.no_build:
        rc = _build_frontend()
        if rc != 0:
            return rc
    return cmd_restart(args)


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
    ws, pb, sa, ev = h.get("workspace", {}), h.get("playbooks", {}), h.get("subagents", {}), h.get("evolution", {})
    print(f"Athena is up at {base_url}  (pid {pid})")
    print(f"  model:    {h.get('llm')}  ({h.get('backend')})")
    print(f"  safety:   {h.get('safety')}   approval: {h.get('approval')}")
    print(f"  ledger:   {h.get('blocks')} signed blocks")
    print(f"  workspace: {'on' if ws.get('enabled') else 'off'}   playbooks: {pb.get('count', 0)} ({'on' if pb.get('enabled') else 'off'})")
    print(f"  agents:   {sa.get('builtin', 0)} built-in + {sa.get('custom', 0)} custom   evolution: {ev.get('learned', 0)} learned"
          + ("  (auto)" if ev.get("auto") else ""))
    cache = h.get("cache", {})
    if cache:
        print(f"  cache:    {'on' if cache.get('enabled') else 'off'}   {cache.get('entries', 0)} answers · {cache.get('hits', 0)} hits")
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
    if not directive and not sys.stdin.isatty():
        directive = sys.stdin.read().strip()  # allow piping: echo "..." | athena run
    if not directive:
        print("Give a directive, e.g.  athena run \"summarize the news\"", file=sys.stderr)
        return 2

    # Scripting paths use the plain blocking endpoint; interactive use streams live.
    if getattr(args, "json", False) or getattr(args, "no_stream", False):
        try:
            payload = _post_json(f"{base_url}/api/task", {"directive": directive})
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return _err("Not signed in. Run:  athena login")
            return _err(_detail(e))
        except urllib.error.URLError:
            return _err(f"Couldn't reach Athena at {base_url}.  Start it with:  athena up")
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print(_format_run_result(payload))
        return 0 if payload.get("success") else 1

    print(style("▸ ", "magenta") + directive)
    result = _render_stream(base_url, directive)
    if result is None:
        return 1
    return 0 if result.get("success") else 1


# --- accounts -------------------------------------------------------------

def cmd_login(args) -> int:
    import getpass
    base_url = f"http://{args.host}:{args.port}"
    email = (args.email or input("Email: ")).strip()
    password = getpass.getpass("Password: ")
    try:
        out = _post_json(f"{base_url}/api/auth/login", {"email": email, "password": password}, timeout=30)
    except urllib.error.HTTPError as e:
        print(_detail(e), file=sys.stderr)
        return 1
    except urllib.error.URLError:
        print(f"Couldn't reach Athena at {base_url}.  Start it with:  athena up", file=sys.stderr)
        return 1
    write_token(out["token"])
    user = out.get("user", {})
    print(f"Signed in as {user.get('name') or user.get('email')}.")
    return 0


def cmd_logout(_args) -> int:
    write_token(None)
    print("Signed out.")
    return 0


def cmd_whoami(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    if not read_token():
        print("Not signed in. Run:  athena login")
        return 1
    try:
        me = _get_json(f"{base_url}/api/auth/me").get("user", {})
    except urllib.error.HTTPError as e:
        print("Session expired. Run:  athena login" if e.code == 401 else _detail(e), file=sys.stderr)
        return 1
    except urllib.error.URLError:
        print("Couldn't reach Athena.  Start it with:  athena up", file=sys.stderr)
        return 1
    print(f"{me.get('name')} <{me.get('email')}>" + ("  (admin)" if me.get("is_admin") else ""))
    return 0


def cmd_chat(args) -> int:
    base_url = args.url or f"http://{args.host}:{args.port}"
    # Keep the whole chat in one session so turns build on each other.
    session_id = None
    try:
        session_id = _get_json(f"{base_url}/api/workspace").get("active_id")
    except Exception:  # noqa: BLE001
        pass
    print(style("Athena chat", "bold") + style("  —  type a task, or 'exit' to quit. Ctrl-C stops a run.\n", "dim"))
    while True:
        try:
            directive = input(style("you ▸ ", "magenta", "bold")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if directive.lower() in ("exit", "quit", ":q"):
            return 0
        if not directive:
            continue
        result = _render_stream(base_url, directive, session_id=session_id)
        if result and result.get("session_id"):
            session_id = result["session_id"]  # stay in the same conversation
        print()


def cmd_messaging(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    try:
        data = _get_json(f"{base_url}/api/messaging")
    except urllib.error.HTTPError as e:
        print("Admin sign-in required. Run:  athena login" if e.code in (401, 403) else _detail(e), file=sys.stderr)
        return 1
    except urllib.error.URLError:
        print("Couldn't reach Athena.  Start it with:  athena up", file=sys.stderr)
        return 1
    if args.action == "list" or not args.platform:
        mark = {"ready": "●", "needs_setup": "◐", "disabled": "○"}
        for p in data["platforms"]:
            st = data["gateways"][p["id"]]["status"]
            print(f"  {mark.get(st, '○')} {p['label']:<16} {p['id']:<12} {st}")
        return 0
    pid = args.platform
    if pid not in {p["id"] for p in data["platforms"]}:
        print(f"Unknown platform {pid!r}. Run:  athena messaging list", file=sys.stderr)
        return 1
    config = {}
    for kv in (args.set or []):
        if "=" in kv:
            k, v = kv.split("=", 1)
            config[k] = v
    out = _post_json(f"{base_url}/api/messaging/{pid}", {"config": config, "enabled": args.action == "enable"})
    print(f"{pid}: {out['gateway']['status']}")
    return 0


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


# --- inspecting the agent ------------------------------------------------

def cmd_sessions(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    ws = _api(base_url, "GET", "/api/workspace")
    if ws is None:
        return 1
    sessions = ws.get("sessions", [])
    if not sessions:
        print(style("No conversations yet.", "dim"))
        return 0
    active = ws.get("active_id")
    for s in sessions:
        mark = style("●", "green") if s["id"] == active else style("○", "gray")
        title = s.get("title") or "Untitled"
        print(f"  {mark} {title}" + style(f"   {s.get('run_count', 0)} turns · {s['id'][:8]}", "dim"))
    return 0


def cmd_agents(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    data = _api(base_url, "GET", "/api/agents")
    if data is None:
        return 1
    agents = data.get("agents", [])
    print(style(f"  {len(agents)} signed agents", "dim"))
    for a in agents:
        print("  " + style(f"{a['role']:<11}", "cyan") + " " + style(a["public_key"][:36] + "…", "gray"))
    return 0


def cmd_skills(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    action = getattr(args, "action", "list") or "list"
    rest = getattr(args, "rest", []) or []

    if action == "synth":
        task = " ".join(rest).strip()
        if not task:
            return _err('Usage:  athena skills synth "reverse a string"')
        print(style("Synthesizing…", "dim"))
        out = _api(base_url, "POST", "/api/skills/synthesize", {"task": task})
        if out is None:
            return 1
        if out.get("ok"):
            c = out.get("stored") or out.get("candidate") or {}
            print(style("✓ synthesized ", "green") + style(c.get("name", "?"), "bold") + style(f"   {c.get('status', '')}", "dim"))
            return 0
        return _err("✗ " + (out.get("reason") or "synthesis failed"))
    if action in ("approve", "reject"):
        if not rest:
            return _err(f"Usage:  athena skills {action} <skill_id>")
        out = _api(base_url, "POST", f"/api/skills/{rest[0]}/{action}")
        if out is None:
            return 1
        print(style(f"✓ {action}d ", "green") + style(out.get("name", ""), "bold") + style(f"   {out.get('status', '')}", "dim"))
        return 0

    path = "/api/skills" + (f"?status={urllib.parse.quote(args.status)}" if getattr(args, "status", None) else "")
    data = _api(base_url, "GET", path)
    if data is None:
        return 1
    skills = data.get("skills", [])
    if not skills:
        print(style("No skills learned yet.", "dim"))
        return 0
    for s in skills:
        pin = style(" 📌", "yellow") if s.get("pinned") else ""
        print("  " + style(s.get("name", "?"), "bold") + style(f"   {s.get('status', '')}", "dim") + pin)
        if s.get("description"):
            print(style(f"     {s['description']}", "dim"))
    return 0


# --- controls + the features I've been building --------------------------

def cmd_safety(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    if args.mode:
        out = _api(base_url, "POST", "/api/safety", {"mode": args.mode.replace("-", "_")})
        if out is None:
            return 1
        print(style("✓ safety: ", "green") + style(out.get("mode", "?"), "bold"))
        return 0
    data = _api(base_url, "GET", "/api/safety")
    if data is None:
        return 1
    print("  safety: " + style(data.get("mode", "?"), "bold") + style("   (" + ", ".join(data.get("modes", [])) + ")", "dim"))
    return 0


def cmd_approval(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    if args.mode:
        out = _api(base_url, "POST", "/api/approval", {"mode": args.mode})
        if out is None:
            return 1
        print(style("✓ approval: ", "green") + style(out.get("mode", "?"), "bold"))
        return 0
    data = _api(base_url, "GET", "/api/approval")
    if data is None:
        return 1
    print("  approval: " + style(data.get("mode", "?"), "bold") + style("   (auto | gated)", "dim"))
    return 0


def cmd_workspace(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    if args.action in ("on", "off"):
        out = _api(base_url, "POST", "/api/fs", {"enabled": args.action == "on"})
        if out is None:
            return 1
        print(style(f"✓ workspace {'enabled' if out.get('enabled') else 'disabled'}", "green") + style(f"   {out.get('root', '')}", "dim"))
        return 0
    data = _api(base_url, "GET", "/api/fs")
    if data is None:
        return 1
    on = data.get("enabled")
    print("  workspace: " + (style("on", "green") if on else style("off", "dim")) + style(f"   {data.get('root', '')}", "dim"))
    if data.get("tools"):
        print(style("  tools: " + ", ".join(data["tools"]), "dim"))
    files = data.get("files", [])
    for f in files[:50]:
        print("  " + style("•", "gray") + " " + f)
    if on and not files:
        print(style("  (no files yet)", "dim"))
    return 0


def cmd_playbooks(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    act = args.action
    if act in ("on", "off"):
        out = _api(base_url, "POST", "/api/playbooks/enabled", {"enabled": act == "on"})
        if out is None:
            return 1
        print(style(f"✓ playbooks {'exposed to the swarm' if out.get('enabled') else 'hidden'}", "green"))
        return 0
    if act == "add":
        if not args.name:
            return _err('Usage:  athena playbooks add <name> --body "..."  [--desc "..."]')
        body = args.body
        if body is None and not sys.stdin.isatty():
            body = sys.stdin.read()
        out = _api(base_url, "POST", "/api/playbooks", {"name": args.name, "description": args.desc or "", "body": body or ""})
        if out is None:
            return 1
        print(style("✓ saved playbook ", "green") + style(out.get("slug", ""), "bold"))
        return 0
    if act == "rm":
        if not args.name:
            return _err("Usage:  athena playbooks rm <slug>")
        if _api(base_url, "DELETE", f"/api/playbooks/{urllib.parse.quote(args.name)}") is None:
            return 1
        print(style("✓ removed ", "green") + args.name)
        return 0
    data = _api(base_url, "GET", "/api/playbooks")
    if data is None:
        return 1
    print("  playbooks " + (style("(exposed to the swarm)", "green") if data.get("enabled") else style("(not exposed)", "dim")))
    for p in data.get("playbooks", []):
        print("  " + style(p.get("name", "?"), "bold") + style(f"   {p.get('slug', '')}", "gray") + (style(f"   {p['description']}", "dim") if p.get("description") else ""))
    if not data.get("playbooks"):
        print(style('  none yet — add with:  athena playbooks add <name> --body "..."', "dim"))
    return 0


def cmd_subagents(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    act = args.action
    if act == "add":
        if not args.name or not args.prompt:
            return _err('Usage:  athena subagents add <name> --prompt "..."  [--desc "..."] [--iters N]')
        out = _api(base_url, "POST", "/api/subagents",
                   {"name": args.name, "description": args.desc or "", "prompt": args.prompt, "iterations": args.iters})
        if out is None:
            return 1
        print(style("✓ saved sub-agent ", "green") + style(out.get("slug", ""), "bold"))
        return 0
    if act == "rm":
        if not args.name:
            return _err("Usage:  athena subagents rm <slug>")
        if _api(base_url, "DELETE", f"/api/subagents/{urllib.parse.quote(args.name)}") is None:
            return 1
        print(style("✓ removed ", "green") + args.name)
        return 0
    data = _api(base_url, "GET", "/api/subagents")
    if data is None:
        return 1
    print(style("  built-in specialists", "dim"))
    for b in data.get("builtin", []):
        print("  " + style(f"{b['role']:<12}", "cyan") + style(b.get("description", ""), "dim"))
    custom = data.get("custom", [])
    if custom:
        print(style("  your sub-agents", "dim"))
        for c in custom:
            print("  " + style(c.get("name", "?"), "bold") + style(f"   {c.get('slug', '')} · {c.get('iterations')} iters", "gray")
                  + (style(f"   {c['description']}", "dim") if c.get("description") else ""))
    return 0


def cmd_evolution(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    act = args.action
    if act == "evolve":
        out = _api(base_url, "POST", "/api/evolution/evolve")
        if out is None:
            return 1
        applied = [k for k in ("routing", "budgets", "lessons", "playbooks", "skills", "retire")
                   if isinstance(out.get(k), dict) and out[k].get("applied")]
        print(style("✓ evolved: ", "green") + ", ".join(applied) if applied else style("no changes warranted yet — run more tasks.", "dim"))
        return 0
    if act == "revert":
        out = _api(base_url, "POST", "/api/evolution/revert")
        if out is None:
            return 1
        print(style("✓ reverted " + (out.get("store", "") or ""), "green") if out.get("reverted") else style(out.get("reason", "nothing to revert"), "dim"))
        return 0
    if act == "auto":
        enabled = (args.value or "").lower() in ("on", "true", "1", "yes")
        out = _api(base_url, "POST", "/api/evolution/auto", {"enabled": enabled, "every": args.every})
        if out is None:
            return 1
        print(style(f"✓ auto-evolve {'on' if out.get('enabled') else 'off'}  (every {out.get('every')} episodes)", "green"))
        return 0
    if act in ("unpin", "unretire"):
        if not args.value:
            return _err(f"Usage:  athena evolution {act} <{'skill_id' if act == 'unpin' else 'role'}>")
        out = _api(base_url, "POST", f"/api/evolution/{act}/{urllib.parse.quote(args.value)}")
        if out is None:
            return 1
        print(style("✓ done", "green"))
        return 0

    data = _api(base_url, "GET", "/api/evolution")
    if data is None:
        return 1
    acc = data.get("accuracy")
    print("  routing accuracy: " + style(f"{round(acc * 100)}%" if acc is not None else "—", "bold")
          + style(f"   {data.get('episodes', 0)} episodes", "dim"))
    lr = data.get("learned", {})
    print(style(f"  learned exemplars: fast {lr.get('fast', 0)} · medium {lr.get('medium', 0)} · full {lr.get('full', 0)}", "dim"))
    if data.get("budgets"):
        print(style("  budgets: " + json.dumps(data["budgets"]), "dim"))
    if data.get("lessons"):
        print(style("  lessons: " + json.dumps(data["lessons"]), "dim"))
    if data.get("pinned_skills"):
        print(style("  pinned tools: " + ", ".join(s.get("name", "?") for s in data["pinned_skills"]), "dim"))
    if data.get("retired"):
        print(style("  retired: " + ", ".join(data["retired"]), "dim"))
    auto = data.get("auto", {})
    print(style(f"  auto-evolve: {'on' if auto.get('enabled') else 'off'} (every {auto.get('every')} episodes)", "dim"))
    return 0


def cmd_cache(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    if args.action == "clear":
        out = _api(base_url, "DELETE", "/api/cache")
        if out is None:
            return 1
        print(style(f"✓ cleared {out.get('cleared', 0)} cached answer(s)", "green"))
        return 0
    if args.action in ("on", "off"):
        out = _api(base_url, "POST", "/api/cache", {"enabled": args.action == "on"})
        if out is None:
            return 1
        print(style(f"✓ answer cache {'on' if out.get('enabled') else 'off'}", "green"))
        return 0
    data = _api(base_url, "GET", "/api/cache")
    if data is None:
        return 1
    on = data.get("enabled")
    print("  answer cache: " + (style("on", "green") if on else style("off", "dim"))
          + style(f"   {data.get('entries', 0)} entries · {data.get('hits', 0)} hits / {data.get('misses', 0)} misses"
                  f" · threshold {data.get('threshold')}", "dim"))
    return 0


def cmd_personas(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    act = getattr(args, "action", "list") or "list"
    if act == "add":
        if not args.name or not args.prompt:
            return _err('Usage:  athena personas add <name> --prompt "..."  [--emoji 🧠]')
        out = _api(base_url, "POST", "/api/personas",
                   {"name": args.name, "instructions": args.prompt, "emoji": args.emoji})
        if out is None:
            return 1
        p = out.get("persona", {})
        print(style("✓ saved persona ", "green") + style(p.get("name", ""), "bold") + style(f"   {p.get('id', '')}", "gray"))
        return 0
    if act == "rm":
        if not args.name:
            return _err("Usage:  athena personas rm <id>")
        if _api(base_url, "DELETE", f"/api/personas/{urllib.parse.quote(args.name)}") is None:
            return 1
        print(style("✓ removed ", "green") + args.name)
        return 0
    ws = _api(base_url, "GET", "/api/workspace")
    if ws is None:
        return 1
    personas = ws.get("personas", [])
    if not personas:
        print(style('No personas yet. Add one:  athena personas add <name> --prompt "..."', "dim"))
        return 0
    for p in personas:
        emoji = (p.get("emoji", "") + " ") if p.get("emoji") else ""
        print("  " + emoji + style(p.get("name", "?"), "bold") + style(f"   {p.get('id', '')}", "gray"))
        instructions = p.get("instructions") or p.get("prompt")
        if instructions:
            print(style(f"     {instructions[:120]}", "dim"))
    return 0


def cmd_memory(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    path = f"/api/memory/{args.layer}"
    if args.query:
        path += "?q=" + urllib.parse.quote(args.query)
    data = _api(base_url, "GET", path)
    if data is None:
        return 1
    items = data.get("items", [])
    if not items:
        print(style(f"No {args.layer} memories" + (" match." if args.query else " yet."), "dim"))
        return 0
    for it in items:
        text = it.get("text") or it.get("name") or json.dumps(it)
        print("  " + style("•", "gray") + " " + text[:200])
    return 0


def cmd_remember(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    text = " ".join(args.text).strip()
    if not text:
        return _err("Give something to remember, e.g.  athena remember \"the API base is /v2\"")
    out = _api(base_url, "POST", f"/api/memory/{args.layer}", {"text": text})
    if out is None:
        return 1
    print(style(f"✓ stored in {args.layer} memory.", "green"))
    return 0


def cmd_search(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    query = " ".join(args.query).strip()
    if not query:
        return _err("Give a search query, e.g.  athena search \"ed25519 vs rsa\"")
    out = _api(base_url, "POST", "/api/mcp/call", {"tool": "web_search", "args": {"query": query, "limit": args.limit}})
    if out is None:
        return 1
    if not out.get("ok"):
        return _err(out.get("error", "search failed"))
    res = out.get("result", {})
    results = res.get("results", [])
    print(style(f"  {len(results)} results via {res.get('provider', '?')}", "dim"))
    for i, r in enumerate(results, 1):
        print("  " + style(f"{i}.", "gray") + " " + style(r.get("title", ""), "bold"))
        print("     " + style(r.get("url", ""), "cyan"))
        if r.get("snippet"):
            print(style(f"     {r['snippet']}", "dim"))
    return 0


def cmd_verify(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    data = _api(base_url, "GET", "/api/ledger")
    if data is None:
        return 1
    ver = data.get("verification") or {}
    ok = ver.get("valid")
    head = style("✓ chain verified", "green") if ok else style("✗ CHAIN INVALID", "red")
    print(head + style(f"   ·   {data.get('count', 0)} signed blocks", "dim"))
    return 0 if ok else 1


def cmd_metrics(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    m = _api(base_url, "GET", "/api/metrics")
    if m is None:
        return 1
    total = int(m.get("tasks_total", 0))
    rate = (m.get("tasks_success", 0) / total * 100) if total else 0
    print("  " + style("tasks ", "dim") + f"  {total}  ({rate:.0f}% success · {m.get('task_duration_avg_s', 0):.1f}s avg)")
    print("  " + style("llm   ", "dim") + f"  {int(m.get('llm_calls', 0))} calls · {int(m.get('tokens_total', 0)):,} tokens · ${m.get('usd_total', 0):.4f}")
    print("  " + style("skills", "dim") + f"  {int(m.get('skills_synthesized', 0))} synthesized")
    print("  " + style("eval  ", "dim") + f"  {int(m.get('eval_runs', 0))} runs · last {m.get('last_pass_rate', 0) * 100:.0f}% pass")
    return 0


def cmd_models(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    if args.set:  # switch model: athena models --set ollama:qwen2.5:7b-instruct  (or  backend model)
        backend, _, model = args.set.partition(":")
        payload = {"backend": backend.strip()}
        if model.strip():
            payload["model"] = model.strip()
        out = _api(base_url, "POST", "/api/llm", payload)
        if out is None:
            return 1
        print(style("✓ model set to ", "green") + style(out.get("model_id", "?"), "bold"))
        return 0
    data = _api(base_url, "GET", "/api/llm")
    if data is None:
        return 1
    print("  current:  " + style(data.get("model_id", "?"), "bold") + style(f"   ({data.get('backend')})", "dim"))
    print(style("  native:   " + ", ".join(data.get("native", [])), "dim"))
    provs = [p.get("id") or p.get("name") for p in (data.get("providers") or [])]
    provs = [p for p in provs if p]
    if provs:
        shown = ", ".join(provs[:16]) + (f", +{len(provs) - 16} more" if len(provs) > 16 else "")
        print(style("  providers: " + shown, "dim"))
    return 0


def cmd_eval(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    print(style("Running the benchmark suite…", "dim"))
    out = _api(base_url, "POST", "/api/eval/run", {})
    if out is None:
        return 1
    run = out.get("run", {})
    pr = run.get("pass_rate", 0)
    head = style("✓", "green") if pr >= 0.5 else style("•", "yellow")
    print(f"  {head}  {run.get('passed', 0)}/{run.get('total', 0)} passed   ({pr * 100:.0f}%)")
    return 0


def cmd_recipes(args) -> int:
    base_url = f"http://{args.host}:{args.port}"
    act = getattr(args, "action", "list") or "list"
    if act == "add":
        if not args.name or not args.prompt:
            return _err('Usage:  athena recipes add <name> --prompt "..."  [--desc "..."] [--emoji 📋]')
        out = _api(base_url, "POST", "/api/recipes",
                   {"name": args.name, "prompt": args.prompt, "description": args.desc or "", "emoji": args.emoji})
        if out is None:
            return 1
        r = out.get("recipe", {})
        print(style("✓ saved recipe ", "green") + style(r.get("name", ""), "bold") + style(f"   {r.get('id', '')}", "gray"))
        return 0
    if act == "rm":
        if not args.name:
            return _err("Usage:  athena recipes rm <id>")
        if _api(base_url, "DELETE", f"/api/recipes/{urllib.parse.quote(args.name)}") is None:
            return 1
        print(style("✓ removed ", "green") + args.name)
        return 0
    ws = _api(base_url, "GET", "/api/workspace")
    if ws is None:
        return 1
    recipes = ws.get("recipes", [])
    if not recipes:
        print(style('No recipes yet. Add one:  athena recipes add <name> --prompt "..."', "dim"))
        return 0
    for r in recipes:
        head = ((r.get("emoji", "") + " ") if r.get("emoji") else "") + style(r.get("name", "?"), "bold")
        print("  " + head + style(f"   {r.get('id', '')}", "gray") + (style(f"   {r['description']}", "dim") if r.get("description") else ""))
        if r.get("prompt"):
            print(style(f"     {r['prompt'][:120]}", "gray"))
    return 0


def cmd_version(_args) -> int:
    print("athena 0.2")
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

    restart = sub.add_parser("restart", help="cleanly stop and start (waits for the port to free)")
    restart.add_argument("--open", action="store_true", help="open the dashboard once it's up")
    restart.set_defaults(func=cmd_restart)

    rebuild = sub.add_parser("rebuild", help="rebuild the frontend, then cleanly restart")
    rebuild.add_argument("--no-build", action="store_true", help="skip the frontend build (just clean-restart)")
    rebuild.add_argument("--open", action="store_true", help="open the dashboard once it's up")
    rebuild.set_defaults(func=cmd_rebuild)

    sub.add_parser("status", help="show whether Athena is running").set_defaults(func=cmd_status)
    sub.add_parser("serve", help="run in the foreground (alias for `up -f`)").set_defaults(
        func=lambda a: cmd_up(argparse.Namespace(**{**vars(a), "foreground": True, "open": False}))
    )
    sub.add_parser("open", help="open the dashboard in a browser").set_defaults(func=cmd_open)
    sub.add_parser("version", help="print the version").set_defaults(func=cmd_version)

    desktop = sub.add_parser("desktop", help="launch the native desktop app")
    desktop.add_argument("--build", action="store_true", help="build a distributable .app instead of running")
    desktop.set_defaults(func=cmd_desktop)

    run = sub.add_parser("run", help="dispatch a directive (streams the run live)")
    run.add_argument("directive", nargs="*", help="what the swarm should do (or pipe via stdin)")
    run.add_argument("--url", help="base URL of a running server (overrides --host/--port)")
    run.add_argument("--json", action="store_true", help="print the raw JSON result (for scripting)")
    run.add_argument("--no-stream", action="store_true", help="wait for the full result instead of streaming")
    run.set_defaults(func=cmd_run)

    chat = sub.add_parser("chat", help="interactive terminal chat with the swarm")
    chat.add_argument("--url", help="base URL of a running server (overrides --host/--port)")
    chat.set_defaults(func=cmd_chat)

    login = sub.add_parser("login", help="sign in to the API (stores a session token)")
    login.add_argument("--email", help="account email (prompts if omitted)")
    login.set_defaults(func=cmd_login)
    sub.add_parser("logout", help="clear the stored session token").set_defaults(func=cmd_logout)
    sub.add_parser("whoami", help="show the signed-in account").set_defaults(func=cmd_whoami)

    msg = sub.add_parser("messaging", help="view/configure messaging gateways (admin)")
    msg.add_argument("action", nargs="?", default="list", choices=["list", "enable", "disable"],
                     help="list gateways, or enable/disable one")
    msg.add_argument("platform", nargs="?", help="platform id (e.g. telegram) for enable/disable")
    msg.add_argument("--set", action="append", metavar="KEY=VALUE", help="set a config field (repeatable)")
    msg.set_defaults(func=cmd_messaging)

    # inspecting / driving the agent
    sub.add_parser("sessions", help="list your conversations").set_defaults(func=cmd_sessions)
    sub.add_parser("agents", help="list the swarm's signed agents").set_defaults(func=cmd_agents)
    sk = sub.add_parser("skills", help="list learned skills, or synth/approve/reject")
    sk.add_argument("action", nargs="?", default="list", choices=["list", "synth", "approve", "reject"])
    sk.add_argument("rest", nargs="*", help="task text (synth) or skill_id (approve/reject)")
    sk.add_argument("--status", help="filter the list by status")
    sk.set_defaults(func=cmd_skills)
    rec = sub.add_parser("recipes", help="saved task templates: list, add, rm")
    rec.add_argument("action", nargs="?", default="list", choices=["list", "add", "rm"])
    rec.add_argument("name", nargs="?", help="name (add) or id (rm)")
    rec.add_argument("--prompt", help="the task-template text (add)")
    rec.add_argument("--desc", help="one-line description (add)")
    rec.add_argument("--emoji", help="an emoji (add)")
    rec.set_defaults(func=cmd_recipes)
    sub.add_parser("verify", help="verify the signed ledger chain").set_defaults(func=cmd_verify)
    sub.add_parser("metrics", help="show usage metrics").set_defaults(func=cmd_metrics)
    sub.add_parser("eval", help="run the benchmark suite").set_defaults(func=cmd_eval)

    mem = sub.add_parser("memory", help="browse a memory layer")
    mem.add_argument("layer", nargs="?", default="semantic", choices=["semantic", "episodic", "procedural"])
    mem.add_argument("query", nargs="?", help="optional search text")
    mem.set_defaults(func=cmd_memory)

    rem = sub.add_parser("remember", help="store a fact in memory")
    rem.add_argument("text", nargs="+", help="what to remember")
    rem.add_argument("--layer", default="semantic", choices=["semantic", "episodic", "procedural"])
    rem.set_defaults(func=cmd_remember)

    srch = sub.add_parser("search", help="search the web via the agent's tools")
    srch.add_argument("query", nargs="+", help="what to search for")
    srch.add_argument("--limit", type=int, default=5, help="number of results (default 5)")
    srch.set_defaults(func=cmd_search)

    models = sub.add_parser("models", help="show or switch the LLM (e.g. --set ollama:qwen2.5:7b-instruct)")
    models.add_argument("--set", metavar="BACKEND[:MODEL]", help="switch backend/model")
    models.set_defaults(func=cmd_models)

    # controls + the newer capabilities (workspace, playbooks, sub-agents, evolution)
    safety_p = sub.add_parser("safety", help="show or set the kill switch (live | dry-run | halted)")
    safety_p.add_argument("mode", nargs="?", choices=["live", "dry-run", "halted"], help="set it (omit to show)")
    safety_p.set_defaults(func=cmd_safety)

    appr = sub.add_parser("approval", help="show or set skill-approval mode (auto | gated)")
    appr.add_argument("mode", nargs="?", choices=["auto", "gated"])
    appr.set_defaults(func=cmd_approval)

    wsp = sub.add_parser("workspace", help="the jailed file workspace: show, on, off")
    wsp.add_argument("action", nargs="?", choices=["on", "off"], help="toggle (omit to show files + tools)")
    wsp.set_defaults(func=cmd_workspace)

    pbp = sub.add_parser("playbooks", help="authored playbooks: list, add, rm, on, off")
    pbp.add_argument("action", nargs="?", default="list", choices=["list", "add", "rm", "on", "off"])
    pbp.add_argument("name", nargs="?", help="name (add) or slug (rm)")
    pbp.add_argument("--desc", help="one-line description (add)")
    pbp.add_argument("--body", help="markdown instructions (add; or pipe via stdin)")
    pbp.set_defaults(func=cmd_playbooks)

    sap = sub.add_parser("subagents", help="custom sub-agents: list, add, rm")
    sap.add_argument("action", nargs="?", default="list", choices=["list", "add", "rm"])
    sap.add_argument("name", nargs="?", help="name (add) or slug (rm)")
    sap.add_argument("--prompt", help="system prompt (add)")
    sap.add_argument("--desc", help="one-line description the router reads (add)")
    sap.add_argument("--iters", type=int, default=8, help="ReAct iteration budget (add)")
    sap.set_defaults(func=cmd_subagents)

    evo = sub.add_parser("evolution", help="self-evolving harness: status, evolve, revert, auto, unpin, unretire")
    evo.add_argument("action", nargs="?", default="status",
                     choices=["status", "evolve", "revert", "auto", "unpin", "unretire"])
    evo.add_argument("value", nargs="?", help="on/off (auto), skill_id (unpin), or role (unretire)")
    evo.add_argument("--every", type=int, default=10, help="auto-evolve cadence in episodes")
    evo.set_defaults(func=cmd_evolution)
    sub.add_parser("evolve", help="run one evolution pass (alias for `evolution evolve`)").set_defaults(
        func=lambda a: cmd_evolution(argparse.Namespace(**{**vars(a), "action": "evolve", "value": None, "every": 10}))
    )

    cache_p = sub.add_parser("cache", help="semantic answer cache: status, on, off, clear")
    cache_p.add_argument("action", nargs="?", default="status", choices=["status", "on", "off", "clear"])
    cache_p.set_defaults(func=cmd_cache)

    per = sub.add_parser("personas", help="saved personas: list, add, rm")
    per.add_argument("action", nargs="?", default="list", choices=["list", "add", "rm"])
    per.add_argument("name", nargs="?", help="name (add) or id (rm)")
    per.add_argument("--prompt", help="the persona's system instructions (add)")
    per.add_argument("--emoji", help="an emoji (add)")
    per.set_defaults(func=cmd_personas)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
