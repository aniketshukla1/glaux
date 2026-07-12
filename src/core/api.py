"""FastAPI backend for the Athena swarm dashboard.

Surfaces the backend subsystems built so far:
- **Swarm + ledger** — dispatch a directive, inspect the signed chain.
- **Safety** — the global kill switch (live / dry_run / halted).
- **Memory** — browse/search/add across the tri-partite layers.
- **Roster** — the agents and their cryptographic identities.

LLM backend: real Claude when ``ANTHROPIC_API_KEY`` is set, otherwise the
offline :class:`DemoLLM` so the dashboard is usable with zero setup.

Run:  PYTHONPATH=src uvicorn core.api:app --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

import urllib.parse

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from core import auth, mailer, oauth, users
from core.messaging import MessagingRegistry
from core.observability import METRICS, log_json

# auth action-token lifetimes
VERIFY_TTL = 2 * 24 * 3600      # email verification link
RESET_TTL = 60 * 60            # password reset link
INVITE_TTL = 7 * 24 * 3600     # team invite link
OAUTH_STATE_TTL = 10 * 60      # CSRF state for the OAuth round-trip


def _signup_policy() -> str:
    # open | invite | closed (after the first/bootstrap account exists)
    val = os.environ.get("ATHENA_SIGNUP", "open").lower()
    return val if val in ("open", "invite", "closed") else "open"

import safety
from agents import (
    Budget,
    BaseAgent,
    GENERALIST_SYSTEM,
    MCPRegistry,
    MCPServerConfig,
    SPECIALISTS,
    Reflector,
    Router,
    Swarm,
    begin_source_capture,
    build_specialists,
    collected_sources,
    configure_search,
    default_browser_client,
    default_local_client,
    search_status,
)
from core.ledger import Ledger
from identity import AgentIdentity
from eval import EvalHarness, EvalRun, lift, load_bench
from llm.demo import DemoLLM
from memory import MemoryManager
from skills import SkillLibrary, SkillSynthesizer

ROLES = ["router", "reflector", "generalist", *SPECIALISTS.keys()]
MEMORY_LAYERS = ("semantic", "episodic", "procedural")
BENCH_DIR = Path(__file__).resolve().parents[2] / "bench"


def _athena_home() -> Path:
    return Path(os.environ.get("ATHENA_HOME", Path.home() / ".athena"))


def _mcp_config_path() -> Path:
    return _athena_home() / "mcp_servers.json"


def _schedules_path() -> Path:
    return _athena_home() / "schedules.json"


def _workspace_path() -> Path:
    return _athena_home() / "workspace.json"


def _llm_config_path() -> Path:
    return _athena_home() / "llm.json"


def _users_path() -> Path:
    return _athena_home() / "users.json"


def _messaging_config_path() -> Path:
    return _athena_home() / "messaging.json"


def _search_config_path() -> Path:
    return _athena_home() / "search.json"


def _metrics_path() -> Path:
    return _athena_home() / "metrics.json"


def _ledger_path() -> Path:
    return _athena_home() / "ledger.jsonl"


def _identities_path() -> Path:
    return _athena_home() / "identities.json"


def _load_identities() -> Optional[dict]:
    """Reconstruct the swarm's persistent agent identities (so the SAME keys keep
    signing the ledger across restarts). None if missing/incomplete."""
    p = _identities_path()
    if not p.exists():
        return None
    try:
        import base58
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        data = json.loads(p.read_text())
        out: dict = {}
        for role in ROLES:
            d = data.get(role)
            if not d:
                continue  # a role added after this file was written — backfill below
            sk = Ed25519PrivateKey.from_private_bytes(base58.b58decode(d["seed"]))
            out[role] = AgentIdentity(sk, d["agent_id"], d.get("namespace", "default"))
        if not out:
            return None  # empty/unusable → regenerate the whole set
        # Backfill any newly-added roles WITHOUT rotating the existing persistent
        # keys (adding an agent role must not silently reset the whole ledger's
        # signing identities).
        added = [r for r in ROLES if r not in out]
        if added:
            for role in added:
                out[role] = AgentIdentity.generate()
            _save_identities(out)
        return out
    except Exception:  # noqa: BLE001 - corrupt/old file → regenerate
        return None


def _save_identities(identities: dict) -> None:
    try:
        data = {
            role: {"seed": ident.signing_key_b58(), "agent_id": ident.agent_id, "namespace": ident.namespace}
            for role, ident in identities.items()
        }
        p = _identities_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2))
        os.chmod(p, 0o600)  # private signing keys
    except OSError:
        pass


def _eval_runs_path() -> Path:
    return _athena_home() / "eval_runs.json"


def _load_eval_runs() -> list:
    p = _eval_runs_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    out = []
    for r in data[-200:]:  # keep history bounded
        try:
            out.append(EvalRun(
                timestamp=r["timestamp"], total=r["total"], passed=r["passed"],
                skill_count=r.get("skill_count", 0),
            ))
        except (KeyError, TypeError):
            continue
    return out


def _save_eval_runs(runs: list) -> None:
    p = _eval_runs_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {"timestamp": r.timestamp, "total": r.total, "passed": r.passed, "skill_count": getattr(r, "skill_count", 0)}
            for r in runs[-200:]
        ]
        p.write_text(json.dumps(payload, indent=2))
    except OSError:
        pass


def _load_search_config() -> dict:
    p = _search_config_path()
    if not p.exists():
        return {"provider": "", "keys": {}}
    try:
        data = json.loads(p.read_text())
        return {"provider": data.get("provider", ""), "keys": dict(data.get("keys") or {})}
    except (json.JSONDecodeError, OSError):
        return {"provider": "", "keys": {}}


def _save_search_config(cfg: dict) -> None:
    p = _search_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"provider": cfg.get("provider", ""), "keys": cfg.get("keys", {})}, indent=2))
    try:
        os.chmod(p, 0o600)  # search API keys are secrets
    except OSError:
        pass


def _user_workspace_path(uid: str) -> Path:
    return _athena_home() / "users" / uid / "workspace.json"


def _auth_secret() -> str:
    """A stable server-side secret for signing session tokens, generated once and
    persisted (0600). Distinct from the agents' Ed25519 keys and the HMAC API
    secret. ATHENA_AUTH_SECRET overrides it (e.g. to share across replicas)."""
    override = os.environ.get("ATHENA_AUTH_SECRET")
    if override:
        return override
    path = _athena_home() / "auth_secret"
    try:
        existing = path.read_text().strip()
        if existing:
            return existing
    except OSError:
        pass
    secret = secrets.token_hex(32)
    try:
        _athena_home().mkdir(parents=True, exist_ok=True)
        path.write_text(secret)
        os.chmod(path, 0o600)
    except OSError:
        pass  # non-writable home: a fresh secret per boot still works for this run
    return secret


# Set per-request by UserAuthMiddleware; read by STATE.sessions to pick the
# signed-in user's private workspace. None => the shared/default workspace.
_current_user_id: ContextVar[Optional[str]] = ContextVar("athena_current_user", default=None)


def _load_persisted_llm_config() -> Optional[dict]:
    """Read the last provider/model the user picked. API keys are NEVER persisted,
    so a saved provider that needs a key relies on the key being in the env."""
    try:
        data = json.loads(_llm_config_path().read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("backend"):
        return None
    return {
        "backend": str(data["backend"]),
        "model": data.get("model"),
        "api_key": None,
        "base_url": data.get("base_url"),
    }


def _persist_llm_config(config: dict) -> None:
    """Remember the selected provider/model across restarts — minus the API key.

    Local model files are deliberately not persisted: the server subprocess is
    gone after a restart, so its base_url would be dead."""
    if config.get("backend") == "localmodel":
        return
    try:
        _athena_home().mkdir(parents=True, exist_ok=True)
        payload = {"backend": config.get("backend"), "model": config.get("model"),
                   "base_url": config.get("base_url")}
        _llm_config_path().write_text(json.dumps(payload, indent=2))
    except OSError:
        pass  # best-effort; a non-writable home just means no persistence


def _fast_llm_config_path() -> Path:
    return _athena_home() / "llm_fast.json"


def _load_persisted_fast_llm_config() -> Optional[dict]:
    """The optional fast/cheap model used for routing + reflection (model tiering).
    None means "use the primary model for everything"."""
    try:
        data = json.loads(_fast_llm_config_path().read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("backend"):
        return None
    return {"backend": str(data["backend"]), "model": data.get("model"),
            "api_key": None, "base_url": data.get("base_url")}


def _persist_fast_llm_config(config: Optional[dict]) -> None:
    try:
        _athena_home().mkdir(parents=True, exist_ok=True)
        if not config:
            _fast_llm_config_path().unlink(missing_ok=True)
            return
        payload = {"backend": config.get("backend"), "model": config.get("model"),
                   "base_url": config.get("base_url")}
        _fast_llm_config_path().write_text(json.dumps(payload, indent=2))
    except OSError:
        pass


def _default_llm_config() -> dict:
    # An explicit env override wins; otherwise restore the last UI choice; else default.
    backend = os.environ.get("ATHENA_LLM")
    if backend is None:
        persisted = _load_persisted_llm_config()
        if persisted is not None:
            return persisted
        backend = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "demo"
    return {
        "backend": backend,
        "model": os.environ.get("ATHENA_MODEL"),
        "api_key": None,
        "base_url": os.environ.get("ATHENA_BASE_URL"),
    }


def _make_llm(config: dict):
    backend = config.get("backend", "demo")
    model = config.get("model")
    if backend == "demo":
        return DemoLLM()
    if backend == "ollama":
        from llm.ollama import OllamaClient

        return OllamaClient(model=model or "llama3.2")
    if backend == "anthropic":
        try:
            from llm.gateway import AnthropicClient

            return AnthropicClient(model=model or "claude-sonnet-4-6")
        except Exception:
            return DemoLLM()
    if backend == "localmodel":
        # a model file served locally; the manager owns the process, we just talk to it
        from llm.providers import OpenAICompatibleClient

        base = config.get("base_url")
        if not base:
            return DemoLLM()
        return OpenAICompatibleClient(base_url=base, model=model or "local", provider="local", api_key=None)
    # any OpenAI-compatible provider in the catalog (or "custom" with a base_url)
    try:
        from llm.providers import make_client

        return make_client(
            backend, model=model, api_key=config.get("api_key"), base_url=config.get("base_url")
        )
    except Exception:
        return DemoLLM()


class WSManager:
    """Broadcasts ledger blocks to connected dashboards. Blocks are appended
    from a worker thread (the swarm runs in a threadpool), so publishing hops
    onto the event loop thread-safely."""

    def __init__(self) -> None:
        self.clients: set = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    def publish(self, message: dict) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._fanout, message)

    def _fanout(self, message: dict) -> None:
        for ws in list(self.clients):
            asyncio.create_task(self._safe_send(ws, message))

    async def _safe_send(self, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_json(message)
        except Exception:
            self.clients.discard(ws)


WS = WSManager()


class _State:
    def __init__(self) -> None:
        # Durable memory + skill library: learned skills must accumulate across
        # restarts for self-improvement to compound (not a throwaway temp dir).
        self.memory_dir = str(_athena_home() / "memory")
        try:
            os.makedirs(self.memory_dir, exist_ok=True)
            self.memory = MemoryManager(self.memory_dir)
        except Exception:  # noqa: BLE001 - corrupt store → fall back to a fresh one
            self.memory_dir = tempfile.mkdtemp(prefix="athena-mem-")
            self.memory = MemoryManager(self.memory_dir)
        self.skills = SkillLibrary(self.memory.procedural)
        self.mcp = MCPRegistry(
            builtin=default_local_client(),
            extra_builtins=[default_browser_client()],
            config_path=_mcp_config_path(),
        )
        self.mcp.load(connect=True)
        METRICS.bind(_metrics_path())  # counters survive restarts → real cumulative data
        self.search_config = _load_search_config()
        configure_search(self.search_config.get("provider", ""), self.search_config.get("keys", {}))
        self.messaging = MessagingRegistry(_messaging_config_path())
        from llm.localmodel import LocalModelManager

        self.local_model = LocalModelManager()
        from core.scheduler import Scheduler

        self.scheduler = Scheduler(run_fn=self._run_scheduled, store_path=_schedules_path())
        self.scheduler.load()
        from core.sessions import SessionStore

        self._SessionStore = SessionStore
        # The shared/default workspace — used before login, by the scheduler, and
        # in system contexts. Each signed-in user gets their own private workspace.
        self._default_store = SessionStore(store_path=_workspace_path())
        self._default_store.load()
        self._user_stores: dict[str, "SessionStore"] = {}
        self.users = users.UserStore(_users_path())
        self.users.ensure_admin()  # keep an existing single-user install's owner as admin
        self.auth_secret = _auth_secret()
        self._cancels: dict[str, threading.Event] = {}  # per-user "stop the running task" flags
        self.eval_runs: list[EvalRun] = _load_eval_runs()  # benchmark history survives restarts
        self.approval_mode = "auto"  # auto | gated (gated => human approves synthesized skills)
        self.llm_config = _default_llm_config()
        # Model tiering: an optional fast/cheap model for routing + reflection.
        self.fast_llm_config = _load_persisted_fast_llm_config()
        self.fast_llm = _make_llm(self.fast_llm_config) if self.fast_llm_config else None
        self._ledger_last_save = 0.0
        self._init_signed_state()

    def aux_llm(self):
        """The fast/cheap model for lightweight roles (router, reflector, quick
        replies), or the primary model when no tier is configured."""
        return self.fast_llm or self.llm

    def _on_ledger_append(self, block: dict) -> None:
        WS.publish({"type": "block", "block": block})  # live stream
        now = time.monotonic()
        if now - self._ledger_last_save > 3.0:  # throttled durable write
            self._ledger_last_save = now
            try:
                self.ledger.save(_ledger_path())
            except Exception:  # noqa: BLE001
                pass

    def _init_signed_state(self) -> None:
        """Load the durable agent identities and the tamper-evident ledger chain
        from disk (or create them), so provenance survives restarts."""
        self.identities = _load_identities()
        if self.identities is None:
            self.identities = {role: AgentIdentity.generate() for role in ROLES}
            _save_identities(self.identities)
        lp = _ledger_path()
        if lp.exists():
            try:
                self.ledger = Ledger.load(lp)
            except Exception:  # noqa: BLE001 - corrupt → start fresh
                self.ledger = Ledger()
        else:
            self.ledger = Ledger()
        self.ledger.on_append = self._on_ledger_append
        self.llm = _make_llm(self.llm_config)

    def reset_ledger(self) -> None:
        """Explicitly wipe the chain and mint fresh identities (also on disk)."""
        self.identities = {role: AgentIdentity.generate() for role in ROLES}
        _save_identities(self.identities)
        self.ledger = Ledger()
        self.ledger.on_append = self._on_ledger_append
        self._ledger_last_save = 0.0
        try:
            self.ledger.save(_ledger_path())
        except Exception:  # noqa: BLE001
            pass
        self.llm = _make_llm(self.llm_config)

    @property
    def sessions(self):
        """The workspace for the current request's signed-in user (resolved from a
        contextvar), or the shared default workspace when there's no user."""
        return self.store_for(_current_user_id.get())

    def store_for(self, uid: Optional[str]):
        if not uid:
            return self._default_store
        store = self._user_stores.get(uid)
        if store is None:
            store = self._SessionStore(store_path=_user_workspace_path(uid))
            store.load()
            self._user_stores[uid] = store
        return store

    def current_user(self):
        return self.users.by_id(_current_user_id.get())

    def cancel_for(self, uid: Optional[str]) -> threading.Event:
        """The per-user 'stop the running task' flag (so one user's Stop doesn't
        cancel another user's task)."""
        key = uid or "_default"
        ev = self._cancels.get(key)
        if ev is None:
            ev = threading.Event()
            self._cancels[key] = ev
        return ev

    def resolve_user_id(self, token: Optional[str]) -> Optional[str]:
        """Validate a session token and return its user id (or None). Rejects
        tokens whose version no longer matches (signed out / password changed)."""
        if not token:
            return None
        payload = users.verify_token(self.auth_secret, token)
        if not payload:
            return None
        user = self.users.by_id(payload.get("uid"))
        if user is None or not user.is_active or user.token_version != payload.get("ver"):
            return None
        return user.id

    def reset_memory(self) -> None:
        shutil.rmtree(self.memory_dir, ignore_errors=True)
        os.makedirs(self.memory_dir, exist_ok=True)
        self.memory = MemoryManager(self.memory_dir)
        self.skills = SkillLibrary(self.memory.procedural)

    def store(self, layer: str):
        if layer not in MEMORY_LAYERS:
            raise HTTPException(status_code=404, detail=f"unknown memory layer {layer!r}")
        return getattr(self.memory, layer)

    def _run_scheduled(self, directive: str) -> dict:
        """Run a scheduled directive through the swarm — same path as a manual
        task, so each run is signed onto the ledger and streamed live."""
        swarm = self.build_swarm()
        result = swarm.run(directive, budget=Budget.from_dict(None))
        return {"final": result.final, "ok": result.success, "cost": result.cost}

    def build_swarm(self) -> Swarm:
        # Model tiering: routing + reflection (and quick replies, which reuse the
        # router's client) go to the fast/cheap model; the specialists that do the
        # actual work use the primary model.
        aux = self.aux_llm()
        router = Router(identity=self.identities["router"], llm=aux, ledger=self.ledger)
        # Register the full specialist roster; the router composes a team per directive.
        specialists = build_specialists(
            identities=self.identities, llm=self.llm, ledger=self.ledger, mcp_client=self.mcp
        )
        reflector = Reflector(identity=self.identities["reflector"], llm=aux, ledger=self.ledger)
        # Medium tier: one capable tool-using agent (primary model) for non-trivial
        # single-focus tasks — handles them directly, skipping planning + reflection.
        generalist = BaseAgent(
            identity=self.identities.get("generalist") or AgentIdentity.generate(),
            llm=self.llm,
            ledger=self.ledger,
            name="generalist",
            system_prompt=GENERALIST_SYSTEM,
            mcp_client=self.mcp,
            max_iterations=6,
            # On-the-fly tool creation: no tool for the job? synthesize + test + use one.
            synthesizer=SkillSynthesizer(self.llm),
            skill_library=self.skills,
        )
        return Swarm(
            router=router,
            specialists=specialists,
            reflector=reflector,
            ledger=self.ledger,
            max_retries=2,  # iterate harder toward an accepted result; budget still bounds it
            synthesizer=SkillSynthesizer(self.llm),
            skill_library=self.skills,
            require_approval=(self.approval_mode == "gated"),
            synthesis_llm=self.llm,  # the final answer uses the primary model
            generalist=generalist,
        )


STATE = _State()

@asynccontextmanager
async def _lifespan(_app):
    WS.set_loop(asyncio.get_running_loop())
    STATE.scheduler.start()
    yield
    STATE.scheduler.stop()
    STATE.mcp.close_all()
    STATE.local_model.stop()
    METRICS.save()  # flush the latest counters on a clean shutdown
    try:
        STATE.ledger.save(_ledger_path())  # persist the full signed chain
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title="Athena Swarm API", version="0.2.0", lifespan=_lifespan)

# Public /api endpoints (no user token / HMAC needed): liveness + the auth
# endpoints themselves, so a client can bootstrap and sign in.
def _is_public_api(path: str) -> bool:
    return path == "/api/health" or path == "/api/auth" or path.startswith("/api/auth/")


def _bearer_from_scope(scope) -> Optional[str]:
    for k, v in scope.get("headers", []):
        if k == b"authorization":
            val = v.decode("latin-1")
            if val.lower().startswith("bearer "):
                return val[7:].strip()
    return None


class UserAuthMiddleware:
    """Resolve the signed-in user from the Bearer token into a contextvar (so
    per-user workspaces work with no change to the route handlers), and require
    auth on /api/* once at least one account exists. A fresh server with no
    accounts stays open so the first signup can happen.

    Pure-ASGI (not BaseHTTPMiddleware) so the contextvar reliably reaches the
    endpoint regardless of downstream task boundaries."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        uid = STATE.resolve_user_id(_bearer_from_scope(scope))
        ctx = _current_user_id.set(uid)
        try:
            if (
                scope["method"] != "OPTIONS"
                and path.startswith("/api/")
                and not _is_public_api(path)
                and uid is None
                and STATE.users.count() > 0
            ):
                resp = JSONResponse({"detail": "authentication required"}, status_code=401)
                await resp(scope, receive, send)
                return
            await self.app(scope, receive, send)
        finally:
            _current_user_id.reset(ctx)


class HMACAuthMiddleware(BaseHTTPMiddleware):
    """Enforce HMAC request signing on /api/* when ATHENA_API_SECRET is set."""

    async def dispatch(self, request, call_next):
        secret = auth.current_secret()
        path = request.url.path
        if (
            secret
            and request.method != "OPTIONS"
            and path.startswith("/api/")
            and not _is_public_api(path)
        ):
            body = await request.body()
            ok = auth.verify(
                secret,
                request.method,
                path,
                request.headers.get(auth.HEADER_TS, ""),
                body,
                request.headers.get(auth.HEADER_SIG, ""),
            )
            if not ok:
                return JSONResponse({"detail": "unauthorized"}, status_code=401)

            async def receive():  # re-inject the consumed body for the route
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive
        return await call_next(request)


app.add_middleware(HMACAuthMiddleware)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.add_middleware(UserAuthMiddleware)  # outermost: sets the user contextvar first


# --- auth / accounts -----------------------------------------------------


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    invite: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    settings: Optional[dict] = None


class PasswordRequest(BaseModel):
    current: str
    new: str


def _auth_payload(user) -> dict:
    token = users.issue_token(STATE.auth_secret, user.id, user.token_version)
    return {"token": token, "user": user.public()}


def _app_base_url(request: Request) -> str:
    """The public origin for building links (verify / reset / oauth callback).
    ATHENA_PUBLIC_URL overrides it for deployments behind a proxy."""
    override = os.environ.get("ATHENA_PUBLIC_URL")
    if override:
        return override.rstrip("/")
    return str(request.base_url).rstrip("/")


def _send_verification(user, base_url: str) -> Optional[str]:
    token = users.issue_action_token(STATE.auth_secret, user.id, "verify", ttl=VERIFY_TTL)
    res = mailer.deliver_link(
        user.email, "Verify your Athena email",
        "Confirm your email to finish setting up your account:",
        f"{base_url}/?verify={urllib.parse.quote(token)}",
    )
    return res.get("dev_link")


@app.get("/api/auth/state")
def auth_state() -> dict:
    """Bootstrap: accounts exist? who's signed in? what login options are on?"""
    user = STATE.current_user()
    return {
        "has_users": STATE.users.count() > 0,
        "authenticated": user is not None,
        "user": user.public() if user else None,
        "oauth": oauth.configured_providers(),
        "signup": _signup_policy(),
        "email_delivery": "smtp" if mailer.smtp_configured() else ("dev" if mailer.dev_mode() else "off"),
    }


@app.post("/api/auth/signup")
def auth_signup(req: SignupRequest, request: Request) -> dict:
    # Registration policy applies only once the bootstrap account exists.
    if STATE.users.count() > 0:
        policy = _signup_policy()
        if policy == "closed":
            raise HTTPException(status_code=403, detail="Sign-ups are closed on this server.")
        if policy == "invite":
            if not (req.invite and users.verify_action_token(STATE.auth_secret, req.invite, "invite")):
                raise HTTPException(status_code=403, detail="A valid invite is required to sign up.")
    try:
        user = STATE.users.create(req.email, req.password, req.name)
    except users.UserError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_json("auth", action="signup", user=user.id)
    out = _auth_payload(user)
    if not user.email_verified:
        out["dev_link"] = _send_verification(user, _app_base_url(request))
    return out


@app.post("/api/auth/login")
def auth_login(req: LoginRequest) -> dict:
    user = STATE.users.authenticate(req.email, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account has been deactivated.")
    return _auth_payload(user)


@app.get("/api/auth/me")
def auth_me() -> dict:
    user = STATE.current_user()
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return {"user": user.public()}


@app.patch("/api/auth/me")
def auth_update_me(req: ProfileRequest) -> dict:
    user = STATE.current_user()
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    try:
        STATE.users.update_profile(user, name=req.name, email=req.email, settings=req.settings)
    except users.UserError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"user": user.public()}


@app.post("/api/auth/password")
def auth_change_password(req: PasswordRequest) -> dict:
    user = STATE.current_user()
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    try:
        STATE.users.change_password(user, req.current, req.new)
    except users.UserError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # changing the password rotated token_version — hand back a fresh token so the
    # caller's current session keeps working while older tokens are invalidated.
    return _auth_payload(user)


@app.post("/api/auth/logout")
def auth_logout() -> dict:
    """Sign out everywhere by rotating the token version (all old tokens die)."""
    user = STATE.current_user()
    if user is not None:
        STATE.users.bump_token_version(user)
    return {"ok": True}


@app.delete("/api/auth/me")
def auth_delete_me() -> dict:
    user = STATE.current_user()
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    STATE._user_stores.pop(user.id, None)
    shutil.rmtree(_user_workspace_path(user.id).parent, ignore_errors=True)
    STATE.users.delete(user.id)
    log_json("auth", action="delete", user=user.id)
    return {"ok": True}


# --- email verification + password reset ---------------------------------


class TokenRequest(BaseModel):
    token: str


class ForgotRequest(BaseModel):
    email: str


class ResetRequest(BaseModel):
    token: str
    password: str


@app.post("/api/auth/verify")
def auth_verify(req: TokenRequest) -> dict:
    payload = users.verify_action_token(STATE.auth_secret, req.token, "verify")
    if not payload:
        raise HTTPException(status_code=400, detail="This verification link is invalid or has expired.")
    user = STATE.users.by_id(payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    STATE.users.mark_verified(user)
    return {"ok": True, "user": user.public()}


@app.post("/api/auth/resend-verification")
def auth_resend_verification(request: Request) -> dict:
    user = STATE.current_user()
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    if user.email_verified:
        return {"ok": True, "already_verified": True}
    return {"ok": True, "dev_link": _send_verification(user, _app_base_url(request))}


@app.post("/api/auth/forgot")
def auth_forgot(req: ForgotRequest, request: Request) -> dict:
    """Always returns ok (never reveals whether an email is registered)."""
    user = STATE.users.by_email(req.email)
    dev_link = None
    if user is not None and user.password_hash:
        token = users.issue_action_token(STATE.auth_secret, user.id, "reset", ttl=RESET_TTL)
        res = mailer.deliver_link(
            user.email, "Reset your Athena password",
            "Use this link to choose a new password:",
            f"{_app_base_url(request)}/?reset={urllib.parse.quote(token)}",
        )
        dev_link = res.get("dev_link")
    return {"ok": True, "dev_link": dev_link}


@app.post("/api/auth/reset")
def auth_reset(req: ResetRequest) -> dict:
    payload = users.verify_action_token(STATE.auth_secret, req.token, "reset")
    if not payload:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    user = STATE.users.by_id(payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    try:
        STATE.users.set_password(user, req.password)
    except users.UserError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _auth_payload(user)  # sign them straight in with a fresh token


# --- social login (OAuth) ------------------------------------------------


def _oauth_redirect_uri(request: Request, provider: str) -> str:
    return f"{_app_base_url(request)}/api/auth/oauth/{provider}/callback"


@app.get("/api/auth/oauth/{provider}/start")
def oauth_start(provider: str, request: Request) -> dict:
    if not oauth.is_configured(provider):
        raise HTTPException(status_code=404, detail=f"{provider} login isn't configured on this server.")
    state = users.issue_action_token(STATE.auth_secret, provider, "oauth", ttl=OAUTH_STATE_TTL)
    return {"url": oauth.authorize_url(provider, _oauth_redirect_uri(request, provider), state)}


@app.get("/api/auth/oauth/{provider}/callback")
def oauth_callback(provider: str, request: Request, code: str = "", state: str = "", error: str = ""):
    base = _app_base_url(request)

    def back(fragment: str):
        return RedirectResponse(f"{base}/?{fragment}")

    if error or not code:
        return back(f"oauth_error={urllib.parse.quote(error or 'cancelled')}")
    payload = users.verify_action_token(STATE.auth_secret, state, "oauth")
    if not payload or payload.get("sub") != provider:
        return back("oauth_error=bad_state")
    try:
        access = oauth.exchange_code(provider, code, _oauth_redirect_uri(request, provider))
        subject, email, name = oauth.fetch_identity(provider, access)
    except oauth.OAuthError as e:
        return back(f"oauth_error={urllib.parse.quote(str(e))}")
    user = STATE.users.by_oauth(provider, subject)
    if user is None and email:
        user = STATE.users.by_email(email)
        if user is not None:
            STATE.users.link_oauth(user, provider, subject)  # link to an existing account
    if user is None:
        user = STATE.users.create_oauth(provider, subject, email or "", name or "")
        log_json("auth", action="oauth_signup", provider=provider, user=user.id)
    if not user.is_active:
        return back("oauth_error=account_disabled")
    token = users.issue_token(STATE.auth_secret, user.id, user.token_version)
    return back(f"token={urllib.parse.quote(token)}")


# --- team / admin user management ----------------------------------------


def _require_admin():
    user = STATE.current_user()
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


class AdminUserPatch(BaseModel):
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


@app.get("/api/admin/users")
def admin_list_users() -> dict:
    _require_admin()
    return {"users": STATE.users.list_public()}


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: str, patch: AdminUserPatch) -> dict:
    admin = _require_admin()
    target = STATE.users.by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if patch.is_admin is not None:
        if not patch.is_admin and target.is_admin and STATE.users.admin_count() <= 1:
            raise HTTPException(status_code=400, detail="There must be at least one admin.")
        STATE.users.set_admin(target, patch.is_admin)
    if patch.is_active is not None:
        if not patch.is_active and target.id == admin.id:
            raise HTTPException(status_code=400, detail="You can't deactivate your own account.")
        STATE.users.set_active(target, patch.is_active)
    return {"user": target.public()}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: str) -> dict:
    admin = _require_admin()
    target = STATE.users.by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Delete your own account from Settings.")
    if target.is_admin and STATE.users.admin_count() <= 1:
        raise HTTPException(status_code=400, detail="There must be at least one admin.")
    STATE._user_stores.pop(target.id, None)
    shutil.rmtree(_user_workspace_path(target.id).parent, ignore_errors=True)
    STATE.users.delete(target.id)
    log_json("auth", action="admin_delete", user=target.id)
    return {"ok": True}


@app.post("/api/admin/invites")
def admin_create_invite(request: Request) -> dict:
    _require_admin()
    token = users.issue_action_token(STATE.auth_secret, "team", "invite", ttl=INVITE_TTL)
    return {"link": f"{_app_base_url(request)}/?invite={urllib.parse.quote(token)}", "expires_in": INVITE_TTL}


# --- messaging gateways (instance-level, admin) --------------------------


def _require_admin_if_users():
    """Messaging config is instance-level: require an admin once accounts exist,
    but stay open on a fresh install (same bootstrap rule as the rest of /api)."""
    if STATE.users.count() > 0:
        _require_admin()


class MessagingConfigRequest(BaseModel):
    config: dict = {}
    enabled: bool = False


@app.get("/api/messaging")
def get_messaging() -> dict:
    _require_admin_if_users()
    return {"platforms": STATE.messaging.catalog(), "gateways": STATE.messaging.all_public()}


@app.post("/api/messaging/{platform}")
def set_messaging(platform: str, req: MessagingConfigRequest) -> dict:
    _require_admin_if_users()
    out = STATE.messaging.set_config(platform, req.config, req.enabled)
    if out is None:
        raise HTTPException(status_code=404, detail=f"unknown messaging platform {platform!r}")
    return {"gateway": out}


# --- web search engine (instance-level) ----------------------------------


class SearchConfigRequest(BaseModel):
    provider: Optional[str] = None  # pin an engine ("" = auto-detect by key)
    keys: Optional[dict] = None     # {provider: api_key}; a blank value keeps the saved key


@app.get("/api/search-engine")
def get_search() -> dict:
    return search_status()  # no secrets — safe for any signed-in user to read


@app.post("/api/search-engine")
def set_search(req: SearchConfigRequest) -> dict:
    _require_admin_if_users()
    cfg = STATE.search_config
    if req.provider is not None:
        cfg["provider"] = (req.provider or "").strip().lower()
    if req.keys:
        keys = dict(cfg.get("keys", {}))
        for k, v in req.keys.items():
            v = (v or "").strip()
            if v:  # blank keeps the existing secret
                keys[k] = v
        cfg["keys"] = keys
    _save_search_config(cfg)
    configure_search(cfg.get("provider", ""), cfg.get("keys", {}))
    return search_status()


# --- models --------------------------------------------------------------


class TaskRequest(BaseModel):
    directive: str
    budget: Optional[dict] = None  # {max_tokens?, max_usd?, max_llm_calls?}
    session_id: Optional[str] = None  # which conversation to record into (default: active)


class SafetyRequest(BaseModel):
    mode: str  # live | dry_run | halted


class MemoryAddRequest(BaseModel):
    text: str
    code: Optional[str] = None  # procedural skills
    metadata: Optional[dict] = None


class SynthesizeRequest(BaseModel):
    task: str


class UseRequest(BaseModel):
    success: bool


class ApprovalModeRequest(BaseModel):
    mode: str  # auto | gated


class LLMRequest(BaseModel):
    backend: str  # demo | ollama | anthropic | <provider id> | custom
    model: Optional[str] = None
    api_key: Optional[str] = None  # in-memory only; never persisted or echoed back
    base_url: Optional[str] = None  # required for "custom"


def _skill_dict(r) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "status": r.status,
        "version": r.version,
        "success_rate": round(r.success_rate, 3),
        "usage_count": r.usage_count,
        "caps": r.caps,
        "sensitive": r.sensitive,
        "parent_skill_id": r.parent_skill_id,
        "code": r.code,
    }


def _verification() -> dict:
    v = STATE.ledger.verify()
    return {"valid": v.valid, "first_bad_index": v.first_bad_index, "reason": v.reason}


def _hit(h) -> dict:
    return {"id": h.id, "text": h.text, "metadata": h.metadata, "similarity": h.similarity}


# --- health / roster -----------------------------------------------------


@app.websocket("/ws")
async def ws_feed(websocket: WebSocket) -> None:
    # Browsers can't set headers on a WS handshake, so the session token arrives
    # as a query param (?token=…). Require it once any account exists.
    if STATE.users.count() > 0 and STATE.resolve_user_id(websocket.query_params.get("token")) is None:
        await websocket.close(code=4401)
        return
    await WS.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # clients don't send; this detects disconnect
    except WebSocketDisconnect:
        WS.disconnect(websocket)
    except Exception:
        WS.disconnect(websocket)


@app.get("/api/auth")
def auth_status() -> dict:
    return {"enabled": auth.current_secret() is not None}


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm": STATE.llm.model_id,
        "live": STATE.llm.model_id != "demo-offline",
        "backend": STATE.llm_config["backend"],
        "safety": safety.current_mode().value,
        "approval": STATE.approval_mode,
        "blocks": len(STATE.ledger),
        "memory": {layer: len(STATE.store(layer).list_all()) for layer in MEMORY_LAYERS},
        "sandbox": _sandbox_status(),
    }


def _sandbox_status() -> dict:
    """Which skill-sandbox backend is active and whether the v2 WASM runtime is
    available (no-ambient-authority isolation)."""
    from sandbox import WasmSandbox

    backend = os.environ.get("ATHENA_SANDBOX_BACKEND", "auto").lower()
    wasm_runtime = WasmSandbox.runtime_available()
    wasm_python = WasmSandbox.python_available()
    if backend in ("wasm", "auto") and wasm_python:
        active = "wasm"
    elif backend == "wasm":
        active = "wasm-unavailable"
    else:
        active = "subprocess"
    return {
        "backend": backend,
        "active": active,
        "wasm_runtime": wasm_runtime,   # can run wasm modules (isolation available)
        "wasm_python": wasm_python,      # can run Python skills in wasm (python.wasm set)
    }


@app.get("/api/agents")
def agents() -> dict:
    return {
        "agents": [
            {
                "role": role,
                "agent_id": ident.agent_id,
                "public_key": ident.public_key_b58,
                "namespace": ident.namespace,
            }
            for role, ident in STATE.identities.items()
        ]
    }


# --- safety (kill switch) ------------------------------------------------


@app.get("/api/safety")
def get_safety() -> dict:
    return {"mode": safety.current_mode().value, "modes": [m.value for m in safety.SafetyMode]}


@app.post("/api/safety")
def set_safety(req: SafetyRequest) -> dict:
    try:
        safety.set_mode(req.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid mode {req.mode!r}")
    return {"mode": safety.current_mode().value}


# --- swarm / ledger ------------------------------------------------------


def _prepare_run(req: TaskRequest):
    """Shared setup for a task: build the swarm, budget, and the (persona/project-
    prefixed) directive. Returns (swarm, budget, run_directive, model_id)."""
    swarm = STATE.build_swarm()
    budget = Budget.from_dict(req.budget)
    # If the target session belongs to a project, prepend its custom instructions
    # as context for the run — but keep the recorded directive clean.
    target_sid = req.session_id or STATE.sessions.active().id
    persona_instr = STATE.sessions.persona_instructions_for(target_sid)
    project_instr = STATE.sessions.project_instructions_for(target_sid)
    prefix = ""
    if persona_instr.strip():
        prefix += f"Assistant persona:\n{persona_instr.strip()}\n\n"
    if project_instr.strip():
        prefix += f"Project instructions:\n{project_instr.strip()}\n\n"
    run_directive = f"{prefix}Task:\n{req.directive}" if prefix else req.directive
    return swarm, budget, run_directive, STATE.llm.model_id


def _finalize_run(req: TaskRequest, result, before: int, sources: list, elapsed: float, model_id: str) -> dict:
    """Record metrics, persist the run, and build the response payload — shared by
    the blocking and streaming task endpoints."""
    new_blocks = [STATE.ledger.block(i) for i in range(before, len(STATE.ledger))]
    outcome = (
        "success" if result.success
        else "cancelled" if result.cancelled
        else "budget_halt" if result.budget_halt
        else "incomplete"
    )
    METRICS.inc("swarm_tasks_total", outcome=outcome)
    METRICS.observe_duration("swarm_task_duration", elapsed)
    METRICS.inc("llm_calls_total", result.cost.get("llm_calls", 0))
    METRICS.inc("llm_tokens_total", result.cost.get("total_tokens", 0))
    METRICS.inc("llm_cost_usd_total", result.cost.get("usd", 0.0))
    for s in result.synthesized:
        if s.get("ok"):
            METRICS.inc("skills_synthesized_total")
    log_json(
        "task", outcome=outcome, blocks=len(new_blocks), duration_s=round(elapsed, 3),
        cost=result.cost, synthesized=len(result.synthesized),
    )
    verification = _verification()
    from core.sessions import Run

    session = STATE.sessions.record_run(
        Run(
            id="", directive=req.directive, final=result.final, success=result.success,
            cost=result.cost, verification=verification, blocks=new_blocks, created_at="",
            model=model_id, canvas=result.canvas, sources=sources,
        ),
        session_id=req.session_id,
    )
    return {
        "success": result.success,
        "final": result.final,
        "cost": result.cost,
        "model": model_id,
        "cancelled": result.cancelled,
        "canvas": result.canvas,
        "sources": sources,
        "budget_halt": result.budget_halt,
        "synthesized": result.synthesized,
        "plan": [s.to_dict() for s in result.plan.steps],
        "steps": [
            {
                "id": sid, "role": sr.step.role, "accepted": sr.accepted,
                "attempts": sr.attempts, "reproducibility": sr.result.reproducibility,
            }
            for sid, sr in result.steps.items()
        ],
        "new_blocks": new_blocks,
        "verification": verification,
        "session_id": session.id,
    }


MAX_DIRECTIVE_CHARS = 16000  # a task instruction; long documents belong in attachments


def _validate_directive(directive: str) -> None:
    """Reject empty or pathologically large directives. A huge directive is
    re-embedded, hashed and signed on every agent iteration, so an unbounded one
    can hang a task (and cost a fortune on a real model) — attachments are the
    right home for long content."""
    if not (directive or "").strip():
        raise HTTPException(status_code=400, detail="directive is required")
    if len(directive) > MAX_DIRECTIVE_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"directive too long ({len(directive)} chars, max {MAX_DIRECTIVE_CHARS}); "
            "attach long documents instead of putting them in the task",
        )


@app.post("/api/task")
async def run_task(req: TaskRequest) -> dict:
    _validate_directive(req.directive)
    before = len(STATE.ledger)
    swarm, budget, run_directive, model_id = _prepare_run(req)
    uid = _current_user_id.get()
    cancel_ev = STATE.cancel_for(uid)
    cancel_ev.clear()  # fresh start; a Stop press during this run sets it

    def _on_token(t: str) -> None:
        WS.publish({"type": "token", "text": t, "uid": uid})  # streamed final answer

    begin_source_capture()  # collect any web pages the swarm browses → citations
    t0 = time.monotonic()
    try:
        result = await run_in_threadpool(
            lambda: swarm.run(run_directive, budget=budget, cancel=cancel_ev.is_set, on_token=_on_token)
        )
    except Exception as exc:  # noqa: BLE001 - surface any backend/LLM failure cleanly
        import traceback
        backend = STATE.llm_config.get("backend", "demo")
        model = STATE.llm_config.get("model") or "(default)"
        METRICS.inc("swarm_tasks_total", outcome="error")
        log_json(
            "task", outcome="error", backend=backend, model=model,
            error=str(exc), traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=502,
            detail=f"The {backend} model {model!r} failed: {exc}",
        ) from exc
    finally:
        WS.publish({"type": "token_end", "uid": uid})  # tell clients the stream is done
    elapsed = time.monotonic() - t0
    sources = collected_sources()  # web pages the swarm actually browsed this run
    return _finalize_run(req, result, before, sources, elapsed, model_id)


@app.post("/api/task/stream")
async def run_task_stream(req: TaskRequest):
    """Same as /api/task but streams Server-Sent Events as the swarm works:
    `start`, live `block` events (each signed agent step), `token` deltas (the
    answer typing out), then a final `done` carrying the full result. Lets the
    CLI render the multi-agent run live with nothing but stdlib urllib."""
    _validate_directive(req.directive)
    before = len(STATE.ledger)
    swarm, budget, run_directive, model_id = _prepare_run(req)
    uid = _current_user_id.get()
    cancel_ev = STATE.cancel_for(uid)
    cancel_ev.clear()
    loop = asyncio.get_running_loop()
    tokens: asyncio.Queue = asyncio.Queue()

    def _on_token(t: str) -> None:
        loop.call_soon_threadsafe(tokens.put_nowait, t)
        WS.publish({"type": "token", "text": t, "uid": uid})

    begin_source_capture()

    def _sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, default=str)}\n\n"

    async def gen():
        t0 = time.monotonic()
        yield _sse({"type": "start", "directive": req.directive, "model": model_id})
        fut = asyncio.create_task(
            run_in_threadpool(lambda: swarm.run(run_directive, budget=budget, cancel=cancel_ev.is_set, on_token=_on_token))
        )
        sent = before

        def _drain_blocks(upto: int):
            out = []
            nonlocal sent
            while sent < upto:
                try:
                    out.append(STATE.ledger.block(sent))
                except Exception:  # noqa: BLE001
                    pass
                sent += 1
            return out

        while not fut.done():
            for blk in _drain_blocks(len(STATE.ledger)):
                yield _sse({"type": "block", "block": blk})
            while not tokens.empty():
                yield _sse({"type": "token", "text": tokens.get_nowait()})
            await asyncio.sleep(0.06)
        # flush whatever's left now that the run is done
        for blk in _drain_blocks(len(STATE.ledger)):
            yield _sse({"type": "block", "block": blk})
        while not tokens.empty():
            yield _sse({"type": "token", "text": tokens.get_nowait()})

        try:
            result = await fut
        except Exception as exc:  # noqa: BLE001
            METRICS.inc("swarm_tasks_total", outcome="error")
            log_json("task", outcome="error", error=str(exc))
            yield _sse({"type": "error", "detail": str(exc)})
            return
        elapsed = time.monotonic() - t0
        sources = collected_sources()
        payload = _finalize_run(req, result, before, sources, elapsed, model_id)
        yield _sse({"type": "done", "result": payload})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/task/stop")
def stop_task() -> dict:
    """Request that the caller's in-flight task stop. The swarm checks this flag
    between steps and the agents between iterations, and unwinds cleanly."""
    STATE.cancel_for(_current_user_id.get()).set()
    return {"ok": True}


@app.get("/api/ledger")
def get_ledger() -> dict:
    return {
        "count": len(STATE.ledger),
        "blocks": STATE.ledger.blocks(),
        "verification": _verification(),
    }


@app.get("/api/ledger/export")
def export_ledger() -> PlainTextResponse:
    """The full signed chain as newline-delimited JSON — a self-contained,
    independently verifiable proof. Re-check it offline with:
        python scripts/verify_ledger.py <file>
    (every line is a block with its Ed25519 signature, signing key and hashes)."""
    lines = [json.dumps(STATE.ledger.block(i)) for i in range(len(STATE.ledger))]
    body = "\n".join(lines) + ("\n" if lines else "")
    return PlainTextResponse(
        body,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="athena-ledger.jsonl"'},
    )


@app.get("/api/block/{index}")
def get_block(index: int) -> dict:
    if index < 0 or index >= len(STATE.ledger):
        raise HTTPException(status_code=404, detail="block index out of range")
    return STATE.ledger.block(index)


@app.delete("/api/ledger")
def reset_ledger() -> dict:
    STATE.reset_ledger()
    return {"status": "reset", "blocks": 0}


# --- memory --------------------------------------------------------------


@app.get("/api/memory/{layer}")
def memory_list(layer: str, q: Optional[str] = None, k: int = 20) -> dict:
    store = STATE.store(layer)
    hits = store.search(q, k=k) if q else store.list_all(limit=k)
    return {"layer": layer, "query": q, "items": [_hit(h) for h in hits]}


@app.post("/api/memory/{layer}")
def memory_add(layer: str, req: MemoryAddRequest) -> dict:
    store = STATE.store(layer)
    meta = req.metadata or {}
    if layer == "semantic":
        rec_id = store.add_fact(req.text, source=meta.get("source"))
    elif layer == "episodic":
        rec_id = store.log(req.text, outcome=meta.get("outcome"), success=meta.get("success"))
    else:  # procedural
        rec_id = store.add_skill(req.text, req.code or "def run():\n    pass\n", description=meta.get("description"))
    return {"id": rec_id, "count": len(store.list_all())}


@app.delete("/api/memory")
def reset_memory() -> dict:
    STATE.reset_memory()
    return {"status": "reset"}


# --- skills (synthesis + curation) ---------------------------------------


@app.get("/api/skills")
def list_skills(status: Optional[str] = None) -> dict:
    return {"skills": [_skill_dict(r) for r in STATE.skills.list(status)]}


@app.post("/api/skills/synthesize")
async def synthesize_skill(req: SynthesizeRequest) -> dict:
    if not req.task.strip():
        raise HTTPException(status_code=400, detail="task is required")
    synth = SkillSynthesizer(STATE.llm)
    res = await run_in_threadpool(synth.synthesize, req.task)
    stored = STATE.skills.add_candidate(res.candidate) if res.ok else None
    if stored is not None:
        METRICS.inc("skills_synthesized_total")
    return {
        "ok": res.ok,
        "reason": res.reason,
        "cap_violations": res.cap_violations,
        "test_results": res.test_results,
        "candidate": (
            {"name": res.candidate.name, "code": res.candidate.code, "caps": res.candidate.caps}
            if res.candidate
            else None
        ),
        "stored": _skill_dict(stored) if stored else None,
    }


@app.post("/api/skills/{skill_id}/use")
def use_skill(skill_id: str, req: UseRequest) -> dict:
    rec = STATE.skills.record_use(skill_id, req.success)
    if rec is None:
        raise HTTPException(status_code=404, detail="unknown skill")
    return _skill_dict(rec)


@app.post("/api/skills/{skill_id}/approve")
def approve_skill(skill_id: str) -> dict:
    rec = STATE.skills.approve(skill_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="no pending skill with that id")
    return _skill_dict(rec)


@app.post("/api/skills/{skill_id}/reject")
def reject_skill(skill_id: str) -> dict:
    rec = STATE.skills.reject(skill_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="no pending skill with that id")
    return _skill_dict(rec)


# --- approval mode (HITL gate) -------------------------------------------


@app.get("/api/approval")
def get_approval() -> dict:
    return {"mode": STATE.approval_mode, "modes": ["auto", "gated"]}


@app.post("/api/approval")
def set_approval(req: ApprovalModeRequest) -> dict:
    if req.mode not in ("auto", "gated"):
        raise HTTPException(status_code=400, detail=f"invalid mode {req.mode!r}")
    STATE.approval_mode = req.mode
    return {"mode": STATE.approval_mode}


# --- LLM backend ---------------------------------------------------------


@app.get("/api/llm")
def get_llm() -> dict:
    from llm.ollama import ollama_status
    from llm.providers import hf_runtimes, provider_catalog

    return {
        "backend": STATE.llm_config["backend"],
        "model": STATE.llm_config.get("model"),
        "model_id": STATE.llm.model_id,
        # optional fast/cheap model for routing + reflection (model tiering)
        "fast": (
            {"backend": STATE.fast_llm_config["backend"], "model_id": STATE.fast_llm.model_id}
            if STATE.fast_llm is not None else None
        ),
        # demo + native clients, then every OpenAI-compatible provider in the catalog
        "native": ["demo", "anthropic", "ollama"],
        "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "ollama": ollama_status(),
        "providers": provider_catalog(),
        # ways to run any Hugging Face model (hosted router or a local server)
        "hf_runtimes": hf_runtimes(),
        # local model file server (.gguf / .safetensors / .bin / .pt) managed by Athena
        "local_model": STATE.local_model.status(),
    }


def _validate_llm_backend(backend: str, api_key: Optional[str], base_url: Optional[str]) -> None:
    """Raise HTTPException(400) if this backend can't be used right now."""
    from llm.providers import PROVIDERS, key_available

    if backend == "ollama":
        from llm.ollama import ollama_status

        status = ollama_status()
        if not status["reachable"]:
            raise HTTPException(
                status_code=400,
                detail=f"Ollama not reachable at {status['host']} — start it with `ollama serve`",
            )
    elif backend == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY is not set")
    elif backend == "demo":
        pass
    elif backend in PROVIDERS:
        provider = PROVIDERS[backend]
        if backend == "custom" and not base_url:
            raise HTTPException(status_code=400, detail="custom backend requires a base_url")
        if provider.requires_key and not key_available(backend, api_key):
            raise HTTPException(
                status_code=400,
                detail=f"{provider.label} needs an API key — provide one or set {provider.key_env}",
            )
    else:
        raise HTTPException(status_code=400, detail=f"unknown backend {backend!r}")


@app.post("/api/llm")
def set_llm(req: LLMRequest) -> dict:
    _validate_llm_backend(req.backend, req.api_key, req.base_url)
    STATE.llm_config = {
        "backend": req.backend,
        "model": req.model,
        "api_key": req.api_key,
        "base_url": req.base_url,
    }
    STATE.llm = _make_llm(STATE.llm_config)
    _persist_llm_config(STATE.llm_config)  # remember across restarts (no key)
    return {"backend": req.backend, "model_id": STATE.llm.model_id}


@app.post("/api/llm/fast")
def set_fast_llm(req: LLMRequest) -> dict:
    """Configure the fast/cheap model used for routing + reflection (model tiering)."""
    _validate_llm_backend(req.backend, req.api_key, req.base_url)
    STATE.fast_llm_config = {
        "backend": req.backend, "model": req.model,
        "api_key": req.api_key, "base_url": req.base_url,
    }
    STATE.fast_llm = _make_llm(STATE.fast_llm_config)
    _persist_fast_llm_config(STATE.fast_llm_config)
    return {"fast": {"backend": req.backend, "model_id": STATE.fast_llm.model_id}}


@app.delete("/api/llm/fast")
def clear_fast_llm() -> dict:
    """Disable model tiering — use the primary model for every role."""
    STATE.fast_llm_config = None
    STATE.fast_llm = None
    _persist_fast_llm_config(None)
    return {"fast": None}


# --- local model files (.gguf / .safetensors / .bin / .pt) ---------------


class LocalModelRequest(BaseModel):
    path: str
    port: Optional[int] = None


@app.post("/api/llm/local/plan")
def local_model_plan(req: LocalModelRequest) -> dict:
    """Preview: what format is this, which runtime serves it, is it installed."""
    return STATE.local_model.plan(req.path)


@app.post("/api/llm/local")
async def local_model_load(req: LocalModelRequest) -> dict:
    from llm.localmodel import LocalModelError

    try:
        status = await run_in_threadpool(STATE.local_model.launch, req.path, port=req.port)
    except LocalModelError as e:
        raise HTTPException(status_code=400, detail=str(e))
    STATE.llm_config = {
        "backend": "localmodel",
        "model": status.get("model"),
        "api_key": None,
        "base_url": status.get("base_url"),
    }
    STATE.llm = _make_llm(STATE.llm_config)
    return {"backend": "localmodel", "model_id": STATE.llm.model_id, "local_model": status}


@app.delete("/api/llm/local")
def local_model_unload() -> dict:
    STATE.local_model.stop()
    STATE.llm_config = {"backend": "demo", "model": None, "api_key": None, "base_url": None}
    STATE.llm = _make_llm(STATE.llm_config)
    return {"ok": True, "backend": "demo"}


# --- scheduled jobs (cron) -----------------------------------------------


class ScheduleRequest(BaseModel):
    directive: str
    schedule: str  # cron expr | @daily/@hourly/... | "every 30m"


class ScheduleEnableRequest(BaseModel):
    enabled: bool


@app.get("/api/schedules")
def list_schedules() -> dict:
    return {"jobs": STATE.scheduler.list(), "running": STATE.scheduler._thread is not None}


@app.post("/api/schedules")
def add_schedule(req: ScheduleRequest) -> dict:
    try:
        job = STATE.scheduler.add(req.directive, req.schedule)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"job": job}


@app.delete("/api/schedules/{job_id}")
def remove_schedule(job_id: str) -> dict:
    if not STATE.scheduler.remove(job_id):
        raise HTTPException(status_code=404, detail=f"unknown job {job_id!r}")
    return {"ok": True, "jobs": STATE.scheduler.list()}


@app.post("/api/schedules/{job_id}/enable")
def enable_schedule(job_id: str, req: ScheduleEnableRequest) -> dict:
    job = STATE.scheduler.set_enabled(job_id, req.enabled)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job {job_id!r}")
    return {"job": job}


@app.post("/api/schedules/{job_id}/run")
async def run_schedule_now(job_id: str) -> dict:
    job = await run_in_threadpool(STATE.scheduler.run_now, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job {job_id!r}")
    return {"job": job}


# --- workspace: projects + sessions --------------------------------------


class ProjectRequest(BaseModel):
    name: str
    instructions: Optional[str] = None


class SessionCreateRequest(BaseModel):
    title: Optional[str] = None
    project_id: Optional[str] = None


class SessionUpdateRequest(BaseModel):
    title: Optional[str] = None
    project_id: Optional[str] = "_keep"  # "_keep" = leave unchanged; null = ungroup
    persona_id: Optional[str] = "_keep"  # "_keep" = unchanged; null = clear persona


class PersonaRequest(BaseModel):
    name: str
    instructions: Optional[str] = None
    emoji: Optional[str] = None


class RecipeRequest(BaseModel):
    name: str
    prompt: Optional[str] = None
    description: Optional[str] = None
    emoji: Optional[str] = None


@app.get("/api/workspace")
def get_workspace() -> dict:
    return STATE.sessions.tree()


@app.post("/api/personas")
def create_persona(req: PersonaRequest) -> dict:
    return {"persona": STATE.sessions.create_persona(req.name, req.instructions or "", req.emoji or "🧠")}


@app.patch("/api/personas/{persona_id}")
def update_persona(persona_id: str, req: PersonaRequest) -> dict:
    p = STATE.sessions.update_persona(persona_id, name=req.name, instructions=req.instructions, emoji=req.emoji)
    if p is None:
        raise HTTPException(status_code=404, detail=f"unknown persona {persona_id!r}")
    return {"persona": p}


@app.delete("/api/personas/{persona_id}")
def delete_persona(persona_id: str) -> dict:
    if not STATE.sessions.delete_persona(persona_id):
        raise HTTPException(status_code=404, detail=f"unknown persona {persona_id!r}")
    return {"ok": True, **STATE.sessions.tree()}


@app.post("/api/recipes")
def create_recipe(req: RecipeRequest) -> dict:
    return {"recipe": STATE.sessions.create_recipe(req.name, req.prompt or "", req.description or "", req.emoji or "📋")}


@app.patch("/api/recipes/{recipe_id}")
def update_recipe(recipe_id: str, req: RecipeRequest) -> dict:
    r = STATE.sessions.update_recipe(recipe_id, name=req.name, prompt=req.prompt, description=req.description, emoji=req.emoji)
    if r is None:
        raise HTTPException(status_code=404, detail=f"unknown recipe {recipe_id!r}")
    return {"recipe": r}


@app.delete("/api/recipes/{recipe_id}")
def delete_recipe(recipe_id: str) -> dict:
    if not STATE.sessions.delete_recipe(recipe_id):
        raise HTTPException(status_code=404, detail=f"unknown recipe {recipe_id!r}")
    return {"ok": True, **STATE.sessions.tree()}


@app.post("/api/projects")
def create_project(req: ProjectRequest) -> dict:
    return {"project": STATE.sessions.create_project(req.name, req.instructions or "")}


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, req: ProjectRequest) -> dict:
    p = STATE.sessions.update_project(project_id, name=req.name, instructions=req.instructions)
    if p is None:
        raise HTTPException(status_code=404, detail=f"unknown project {project_id!r}")
    return {"project": p}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    if not STATE.sessions.delete_project(project_id):
        raise HTTPException(status_code=404, detail=f"unknown project {project_id!r}")
    return {"ok": True, **STATE.sessions.tree()}


@app.post("/api/sessions")
def create_session(req: SessionCreateRequest) -> dict:
    s = STATE.sessions.create_session(title=req.title, project_id=req.project_id)
    return {"session": STATE.sessions.session_meta(s), "active_id": STATE.sessions.active_id}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    s = STATE.sessions.session_full(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"unknown session {session_id!r}")
    return {"session": s}


@app.post("/api/sessions/{session_id}/activate")
def activate_session(session_id: str) -> dict:
    if STATE.sessions.activate(session_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown session {session_id!r}")
    return {"active_id": session_id}


@app.patch("/api/sessions/{session_id}")
def update_session(session_id: str, req: SessionUpdateRequest) -> dict:
    s = STATE.sessions.update_session(session_id, title=req.title, project_id=req.project_id, persona_id=req.persona_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"unknown session {session_id!r}")
    return {"session": s}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    if not STATE.sessions.delete_session(session_id):
        raise HTTPException(status_code=404, detail=f"unknown session {session_id!r}")
    return {"ok": True, **STATE.sessions.tree()}


class PinRequest(BaseModel):
    pinned: bool


@app.post("/api/sessions/{session_id}/pin")
def pin_session(session_id: str, req: PinRequest) -> dict:
    s = STATE.sessions.set_pinned(session_id, req.pinned)
    if s is None:
        raise HTTPException(status_code=404, detail=f"unknown session {session_id!r}")
    return {"session": s}


@app.get("/api/search")
def search_conversations(q: str = "") -> dict:
    """Search the signed-in user's conversations by title and message content."""
    return {"results": STATE.sessions.search(q)}


# --- MCP tools -----------------------------------------------------------


class MCPCallRequest(BaseModel):
    tool: str
    args: Optional[dict] = None


@app.get("/api/mcp/tools")
def mcp_tools() -> dict:
    return {"tools": [t.to_dict() for t in STATE.mcp.list_tools()]}


@app.post("/api/mcp/call")
def mcp_call(req: MCPCallRequest) -> dict:
    result = STATE.mcp.call_tool(req.tool, req.args or {})
    METRICS.inc("mcp_calls_total", outcome="ok" if result.get("ok") else "error")
    return result


class MCPServerRequest(BaseModel):
    name: str
    transport: str = "stdio"  # stdio | http
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict] = None
    url: Optional[str] = None
    headers: Optional[dict] = None


@app.get("/api/mcp/servers")
def mcp_servers() -> dict:
    return {"servers": STATE.mcp.statuses()}


@app.post("/api/mcp/servers")
async def mcp_add_server(req: MCPServerRequest) -> dict:
    if not req.name.strip():
        raise HTTPException(status_code=422, detail="server name is required")
    config = MCPServerConfig(
        name=req.name.strip(),
        transport=req.transport,
        command=req.command,
        args=req.args or [],
        env=req.env or {},
        url=req.url,
        headers=req.headers or {},
    )
    # connecting spawns a process / opens a socket — keep it off the event loop
    status = await run_in_threadpool(STATE.mcp.add_server, config)
    return {"server": status}


@app.delete("/api/mcp/servers/{name}")
def mcp_remove_server(name: str) -> dict:
    STATE.mcp.remove_server(name)
    return {"ok": True, "servers": STATE.mcp.statuses()}


@app.post("/api/mcp/servers/{name}/reconnect")
async def mcp_reconnect_server(name: str) -> dict:
    try:
        status = await run_in_threadpool(STATE.mcp.reconnect, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown MCP server {name!r}")
    return {"server": status}


# --- observability -------------------------------------------------------


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    return METRICS.render_prometheus()


@app.get("/api/metrics")
def metrics_json() -> dict:
    m = METRICS
    duration_count = m.value("swarm_task_duration_seconds_count")
    avg = (m.value("swarm_task_duration_seconds_sum") / duration_count) if duration_count else 0.0
    return {
        "tasks_total": m.total("swarm_tasks_total"),
        "tasks_success": m.value("swarm_tasks_total", outcome="success"),
        "tasks_incomplete": m.value("swarm_tasks_total", outcome="incomplete"),
        "tasks_budget_halt": m.value("swarm_tasks_total", outcome="budget_halt"),
        "task_duration_avg_s": round(avg, 3),
        "llm_calls": m.value("llm_calls_total"),
        "tokens_total": m.value("llm_tokens_total"),
        "usd_total": round(m.value("llm_cost_usd_total"), 6),
        "skills_synthesized": m.value("skills_synthesized_total"),
        "eval_runs": m.value("eval_runs_total"),
        "last_pass_rate": m.value("eval_pass_rate"),
    }


# --- evaluation harness --------------------------------------------------


@app.post("/api/eval/run")
async def run_eval() -> dict:
    cases = load_bench(BENCH_DIR)
    harness = EvalHarness(STATE.skills)
    previous = STATE.eval_runs[-1] if STATE.eval_runs else None
    run = await run_in_threadpool(harness.run_suite, cases)
    run.skill_count = len(STATE.skills.list(None))  # capability size at this run
    STATE.eval_runs.append(run)
    _save_eval_runs(STATE.eval_runs)  # persist benchmark history
    METRICS.inc("eval_runs_total")
    METRICS.set("eval_pass_rate", run.pass_rate)
    log_json("eval", passed=run.passed, total=run.total, pass_rate=round(run.pass_rate, 3), skills=run.skill_count)
    return {"run": run.to_dict(), "lift": lift(run, previous)}


def _capability_lift() -> Optional[dict]:
    """How much the agent has improved as it learned skills: pass rate now vs the
    first recorded benchmark, alongside how the library grew. This is the proof
    that the self-improvement loop compounds."""
    runs = STATE.eval_runs
    if len(runs) < 2:
        return None
    first, last = runs[0], runs[-1]
    return {
        "first_pass_rate": round(first.pass_rate, 4),
        "last_pass_rate": round(last.pass_rate, 4),
        "delta": round(last.pass_rate - first.pass_rate, 4),
        "skills_first": getattr(first, "skill_count", 0),
        "skills_last": getattr(last, "skill_count", 0),
        "runs": len(runs),
    }


@app.get("/api/eval/runs")
def eval_runs() -> dict:
    return {
        "runs": [
            {
                "timestamp": r.timestamp, "pass_rate": round(r.pass_rate, 4),
                "passed": r.passed, "total": r.total, "skill_count": getattr(r, "skill_count", 0),
            }
            for r in STATE.eval_runs
        ],
        "lift": _capability_lift(),
    }


# --- serve the built dashboard -------------------------------------------
# When the frontend has been built (`npm run build` -> frontend/dist), serve it
# from the same origin so `athena up` gives the user one URL for UI + API.
# Mounted last so /api/*, /ws and /metrics keep precedence over the catch-all.


def _frontend_dist() -> Path:
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


_DIST = _frontend_dist()
if _DIST.is_dir():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    _INDEX = _DIST / "index.html"
    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}

    # index.html must NEVER be cached: a WebView/browser that caches it keeps
    # booting an old build that points at stale (now-deleted) hashed bundles, so
    # the app looks "not updated" after a rebuild. The /assets/* files are
    # content-hashed and immutable, so StaticFiles may cache those freely.
    @app.get("/", include_in_schema=False)
    def _spa_index() -> FileResponse:
        return FileResponse(_INDEX, headers=_NO_CACHE)

    # Mounted last so /api/*, /ws and /metrics keep precedence over the catch-all.
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
