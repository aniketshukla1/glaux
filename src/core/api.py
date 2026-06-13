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
import os
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

from core import auth
from core.observability import METRICS, log_json

import safety
from agents import (
    Budget,
    MCPRegistry,
    MCPServerConfig,
    Reflector,
    Router,
    Swarm,
    coder_agent,
    default_local_client,
    researcher_agent,
)
from core.ledger import Ledger
from identity import AgentIdentity
from eval import EvalHarness, EvalRun, lift, load_bench
from llm.demo import DemoLLM
from memory import MemoryManager
from skills import SkillLibrary, SkillSynthesizer

ROLES = ["router", "coder", "researcher", "reflector"]
MEMORY_LAYERS = ("semantic", "episodic", "procedural")
BENCH_DIR = Path(__file__).resolve().parents[2] / "bench"


def _athena_home() -> Path:
    return Path(os.environ.get("ATHENA_HOME", Path.home() / ".athena"))


def _mcp_config_path() -> Path:
    return _athena_home() / "mcp_servers.json"


def _schedules_path() -> Path:
    return _athena_home() / "schedules.json"


def _default_llm_config() -> dict:
    backend = os.environ.get("ATHENA_LLM")
    if backend is None:
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
        self.memory_dir = tempfile.mkdtemp(prefix="athena-mem-")
        self.memory = MemoryManager(self.memory_dir)
        self.skills = SkillLibrary(self.memory.procedural)
        self.mcp = MCPRegistry(builtin=default_local_client(), config_path=_mcp_config_path())
        self.mcp.load(connect=True)
        from llm.localmodel import LocalModelManager

        self.local_model = LocalModelManager()
        from core.scheduler import Scheduler

        self.scheduler = Scheduler(run_fn=self._run_scheduled, store_path=_schedules_path())
        self.scheduler.load()
        self.eval_runs: list[EvalRun] = []
        self.approval_mode = "auto"  # auto | gated (gated => human approves synthesized skills)
        self.llm_config = _default_llm_config()
        self.reset_ledger()

    def reset_ledger(self) -> None:
        self.ledger = Ledger(on_append=lambda block: WS.publish({"type": "block", "block": block}))
        self.identities = {role: AgentIdentity.generate() for role in ROLES}
        self.llm = _make_llm(self.llm_config)

    def reset_memory(self) -> None:
        shutil.rmtree(self.memory_dir, ignore_errors=True)
        self.memory_dir = tempfile.mkdtemp(prefix="athena-mem-")
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
        router = Router(identity=self.identities["router"], llm=self.llm, ledger=self.ledger)
        coder = coder_agent(
            identity=self.identities["coder"], llm=self.llm, ledger=self.ledger, mcp_client=self.mcp
        )
        researcher = researcher_agent(
            identity=self.identities["researcher"], llm=self.llm, ledger=self.ledger, mcp_client=self.mcp
        )
        reflector = Reflector(identity=self.identities["reflector"], llm=self.llm, ledger=self.ledger)
        return Swarm(
            router=router,
            specialists={"coder": coder, "researcher": researcher},
            reflector=reflector,
            ledger=self.ledger,
            synthesizer=SkillSynthesizer(self.llm),
            skill_library=self.skills,
            require_approval=(self.approval_mode == "gated"),
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


app = FastAPI(title="Athena Swarm API", version="0.2.0", lifespan=_lifespan)

# Public (never signed): liveness + auth-state discovery so a client can bootstrap.
_AUTH_EXEMPT = {"/api/auth", "/api/health"}


class HMACAuthMiddleware(BaseHTTPMiddleware):
    """Enforce HMAC request signing on /api/* when ATHENA_API_SECRET is set."""

    async def dispatch(self, request, call_next):
        secret = auth.current_secret()
        path = request.url.path
        if (
            secret
            and request.method != "OPTIONS"
            and path.startswith("/api/")
            and path not in _AUTH_EXEMPT
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


# --- models --------------------------------------------------------------


class TaskRequest(BaseModel):
    directive: str
    budget: Optional[dict] = None  # {max_tokens?, max_usd?, max_llm_calls?}


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


@app.post("/api/task")
async def run_task(req: TaskRequest) -> dict:
    if not req.directive.strip():
        raise HTTPException(status_code=400, detail="directive is required")
    before = len(STATE.ledger)
    swarm = STATE.build_swarm()
    budget = Budget.from_dict(req.budget)
    t0 = time.monotonic()
    result = await run_in_threadpool(lambda: swarm.run(req.directive, budget=budget))
    elapsed = time.monotonic() - t0
    new_blocks = [STATE.ledger.block(i) for i in range(before, len(STATE.ledger))]

    outcome = "success" if result.success else ("budget_halt" if result.budget_halt else "incomplete")
    METRICS.inc("swarm_tasks_total", outcome=outcome)
    METRICS.observe_duration("swarm_task_duration", elapsed)
    METRICS.inc("llm_calls_total", result.cost.get("llm_calls", 0))
    METRICS.inc("llm_tokens_total", result.cost.get("total_tokens", 0))
    METRICS.inc("llm_cost_usd_total", result.cost.get("usd", 0.0))
    for s in result.synthesized:
        if s.get("ok"):
            METRICS.inc("skills_synthesized_total")
    log_json(
        "task",
        outcome=outcome,
        blocks=len(new_blocks),
        duration_s=round(elapsed, 3),
        cost=result.cost,
        synthesized=len(result.synthesized),
    )
    return {
        "success": result.success,
        "final": result.final,
        "cost": result.cost,
        "budget_halt": result.budget_halt,
        "synthesized": result.synthesized,
        "plan": [s.to_dict() for s in result.plan.steps],
        "steps": [
            {
                "id": sid,
                "role": sr.step.role,
                "accepted": sr.accepted,
                "attempts": sr.attempts,
                "reproducibility": sr.result.reproducibility,
            }
            for sid, sr in result.steps.items()
        ],
        "new_blocks": new_blocks,
        "verification": _verification(),
    }


@app.get("/api/ledger")
def get_ledger() -> dict:
    return {
        "count": len(STATE.ledger),
        "blocks": STATE.ledger.blocks(),
        "verification": _verification(),
    }


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


@app.post("/api/llm")
def set_llm(req: LLMRequest) -> dict:
    from llm.providers import PROVIDERS, key_available

    backend = req.backend
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
        if backend == "custom" and not req.base_url:
            raise HTTPException(status_code=400, detail="custom backend requires a base_url")
        if provider.requires_key and not key_available(backend, req.api_key):
            raise HTTPException(
                status_code=400,
                detail=f"{provider.label} needs an API key — provide one or set {provider.key_env}",
            )
    else:
        raise HTTPException(status_code=400, detail=f"unknown backend {backend!r}")

    STATE.llm_config = {
        "backend": backend,
        "model": req.model,
        "api_key": req.api_key,
        "base_url": req.base_url,
    }
    STATE.llm = _make_llm(STATE.llm_config)
    return {"backend": backend, "model_id": STATE.llm.model_id}


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
    STATE.eval_runs.append(run)
    METRICS.inc("eval_runs_total")
    METRICS.set("eval_pass_rate", run.pass_rate)
    log_json("eval", passed=run.passed, total=run.total, pass_rate=round(run.pass_rate, 3))
    return {"run": run.to_dict(), "lift": lift(run, previous)}


@app.get("/api/eval/runs")
def eval_runs() -> dict:
    return {
        "runs": [
            {"timestamp": r.timestamp, "pass_rate": round(r.pass_rate, 4), "passed": r.passed, "total": r.total}
            for r in STATE.eval_runs
        ]
    }


# --- serve the built dashboard -------------------------------------------
# When the frontend has been built (`npm run build` -> frontend/dist), serve it
# from the same origin so `athena up` gives the user one URL for UI + API.
# Mounted last so /api/*, /ws and /metrics keep precedence over the catch-all.


def _frontend_dist() -> Path:
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


_DIST = _frontend_dist()
if _DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
