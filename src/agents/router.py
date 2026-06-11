"""Router / planner: decomposes a directive into a signed DAG of subtasks.

A single LLM call produces a plan — a list of steps, each assigned to a
specialist role, with `depends_on` edges. The plan is signed onto the ledger
before execution, so the swarm's decomposition is itself auditable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

from core.ledger import Action, Ledger
from identity.keypair import AgentIdentity
from llm.gateway import LLMClient, Message

from .budget import BudgetTracker, charge_for_response
from .protocol import extract_json

ROUTER_SYSTEM = """You are the router for the Athena swarm. Decompose the user's
directive into a minimal plan of subtasks. Respond with a single JSON object in a
```json block of the form:
{"plan": [{"id": "s1", "role": "<role>", "task": "<what to do>", "depends_on": []}]}
Use only the provided roles. `depends_on` lists ids of steps that must finish first."""


@dataclass
class Step:
    id: str
    role: str
    task: str
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "role": self.role, "task": self.task, "depends_on": self.depends_on}


@dataclass
class Plan:
    steps: list[Step]
    raw: str = ""


class Router:
    def __init__(
        self,
        *,
        identity: AgentIdentity,
        llm: LLMClient,
        ledger: Optional[Ledger] = None,
        name: str = "router",
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> None:
        self.identity = identity
        self.llm = llm
        self.ledger = ledger
        self.name = name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.budget: Optional[BudgetTracker] = None  # set by the Swarm per task

    def plan(self, directive: str, *, roles: Optional[list[str]] = None) -> Plan:
        roles = roles or []
        content = f"DIRECTIVE: {directive}\nAVAILABLE ROLES: {', '.join(roles) or 'any'}"
        messages = [Message(role="user", content=content)]
        resp = self.llm.complete(
            messages, system=ROUTER_SYSTEM, temperature=self.temperature, max_tokens=self.max_tokens
        )
        charge_for_response(self.budget, resp, ROUTER_SYSTEM, messages)
        data = extract_json(resp.text) or {}
        steps = [
            Step(
                id=str(s.get("id", f"s{i}")),
                role=str(s.get("role", "")),
                task=str(s.get("task", "")),
                depends_on=list(s.get("depends_on", [])),
            )
            for i, s in enumerate(data.get("plan", []))
        ]
        if self.ledger is not None:
            prompt_hash = hashlib.sha256((ROUTER_SYSTEM + content).encode()).hexdigest()
            self.ledger.append(
                self.identity,
                Action.PLAN,
                {
                    "directive": directive,
                    "plan": [s.to_dict() for s in steps],
                    "prompt_hash": prompt_hash,
                    "model_id": resp.model_id,
                },
            )
        return Plan(steps=steps, raw=resp.text)
