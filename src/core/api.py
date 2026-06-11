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
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import safety
from agents import Reflector, Router, Swarm, coder_agent, researcher_agent
from core.ledger import Ledger
from identity import AgentIdentity
from llm.demo import DemoLLM
from memory import MemoryManager

ROLES = ["router", "coder", "researcher", "reflector"]
MEMORY_LAYERS = ("semantic", "episodic", "procedural")


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
        self.reset_ledger()

    def reset_ledger(self) -> None:
        self.ledger = Ledger()
        self.identities = {role: AgentIdentity.generate() for role in ROLES}
        self.llm = _make_llm()

    def reset_memory(self) -> None:
        shutil.rmtree(self.memory_dir, ignore_errors=True)
        self.memory_dir = tempfile.mkdtemp(prefix="athena-mem-")
        self.memory = MemoryManager(self.memory_dir)

    def store(self, layer: str):
        if layer not in MEMORY_LAYERS:
            raise HTTPException(status_code=404, detail=f"unknown memory layer {layer!r}")
        return getattr(self.memory, layer)

    def build_swarm(self) -> Swarm:
        router = Router(identity=self.identities["router"], llm=self.llm, ledger=self.ledger)
        coder = coder_agent(identity=self.identities["coder"], llm=self.llm, ledger=self.ledger)
        researcher = researcher_agent(
            identity=self.identities["researcher"], llm=self.llm, ledger=self.ledger
        )
        reflector = Reflector(identity=self.identities["reflector"], llm=self.llm, ledger=self.ledger)
        return Swarm(
            router=router,
            specialists={"coder": coder, "researcher": researcher},
            reflector=reflector,
            ledger=self.ledger,
        )


STATE = _State()

app = FastAPI(title="Athena Swarm API", version="0.2.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# --- models --------------------------------------------------------------


class TaskRequest(BaseModel):
    directive: str


class SafetyRequest(BaseModel):
    mode: str  # live | dry_run | halted


class MemoryAddRequest(BaseModel):
    text: str
    code: Optional[str] = None  # procedural skills
    metadata: Optional[dict] = None


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
    result = await run_in_threadpool(swarm.run, req.directive)
    new_blocks = [STATE.ledger.block(i) for i in range(before, len(STATE.ledger))]
    return {
        "success": result.success,
        "final": result.final,
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
