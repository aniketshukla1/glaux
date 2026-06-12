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

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from core.observability import METRICS, log_json

import safety
from agents import (
    Budget,
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


def _make_llm():
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from llm.gateway import AnthropicClient

            return AnthropicClient(model=os.environ.get("ATHENA_MODEL", "claude-sonnet-4-6"))
        except Exception:
            pass
    return DemoLLM()


class _State:
    def __init__(self) -> None:
        self.memory_dir = tempfile.mkdtemp(prefix="athena-mem-")
        self.memory = MemoryManager(self.memory_dir)
        self.skills = SkillLibrary(self.memory.procedural)
        self.mcp = default_local_client()
        self.eval_runs: list[EvalRun] = []
        self.approval_mode = "auto"  # auto | gated (gated => human approves synthesized skills)
        self.reset_ledger()

    def reset_ledger(self) -> None:
        self.ledger = Ledger()
        self.identities = {role: AgentIdentity.generate() for role in ROLES}
        self.llm = _make_llm()

    def reset_memory(self) -> None:
        shutil.rmtree(self.memory_dir, ignore_errors=True)
        self.memory_dir = tempfile.mkdtemp(prefix="athena-mem-")
        self.memory = MemoryManager(self.memory_dir)
        self.skills = SkillLibrary(self.memory.procedural)

    def store(self, layer: str):
        if layer not in MEMORY_LAYERS:
            raise HTTPException(status_code=404, detail=f"unknown memory layer {layer!r}")
        return getattr(self.memory, layer)

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

app = FastAPI(title="Athena Swarm API", version="0.2.0")
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


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm": STATE.llm.model_id,
        "live": STATE.llm.model_id != "demo-offline",
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
