"""FastAPI backend for the Athena swarm dashboard.

Dispatch a directive, run the swarm, and inspect the signed ledger it produces.
Agents reuse stable identities across requests, so the ledger is one continuous,
verifiable chain you can audit in the UI.

LLM backend: real Claude when ``ANTHROPIC_API_KEY`` is set, otherwise the
offline :class:`DemoLLM` so the dashboard is usable with zero setup.

Run:  PYTHONPATH=src uvicorn core.api:app --port 8000 --reload
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from agents import Reflector, Router, Swarm, coder_agent, researcher_agent
from core.ledger import Ledger
from identity import AgentIdentity
from llm.demo import DemoLLM

ROLES = ["router", "coder", "researcher", "reflector"]


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
        self.reset()

    def reset(self) -> None:
        self.ledger = Ledger()
        self.identities = {role: AgentIdentity.generate() for role in ROLES}
        self.llm = _make_llm()

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

app = FastAPI(title="Athena Swarm API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskRequest(BaseModel):
    directive: str


def _verification() -> dict:
    v = STATE.ledger.verify()
    return {"valid": v.valid, "first_bad_index": v.first_bad_index, "reason": v.reason}


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm": STATE.llm.model_id,
        "live": STATE.llm.model_id != "demo-offline",
        "blocks": len(STATE.ledger),
        "agents": {role: ident.agent_id for role, ident in STATE.identities.items()},
    }


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
    STATE.reset()
    return {"status": "reset", "blocks": 0}
