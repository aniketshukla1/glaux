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

ROUTER_SYSTEM = """You are the router for the Athena swarm. You assemble a team of
specialists to complete the user's directive, and you assign each step to the role
best equipped for it.

Scale the team to the work:
- A simple, single-purpose request → ONE step, one specialist. Never pad a trivial task.
- A complex, real-world directive (deep research, system design, multi-part analysis,
  build-and-verify) → break it into the distinct phases it genuinely needs and assign
  each phase to the right specialist, e.g. gather → analyze → build → test → write up.
  Wire `depends_on` so later steps build on the outputs of earlier ones.

Match the phases to what is actually asked: only add a build/implement step when the
request is to build something, and only add a test step when there is something built to
verify. A request to PLAN, EXPLAIN, COMPARE, or RESEARCH needs analysis and a write-up —
not implementation or testing. End a multi-step plan with the role that produces the
deliverable the user asked for (e.g. the planner/analyst/writer), so the final answer is
the answer — not a side artifact.

Prefer the fewest steps that complete the task rigorously — but do not collapse genuinely
distinct phases into one, and do not hand a step to a role that is wrong for it. Respond
with a single JSON object in a ```json block of the form:
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

    def plan(
        self,
        directive: str,
        *,
        roles: Optional[list[str]] = None,
        role_catalog: Optional[dict[str, str]] = None,
    ) -> Plan:
        roles = roles or []
        if role_catalog:
            roster = "\n".join(f"- {r}: {desc}" for r, desc in role_catalog.items())
            content = f"DIRECTIVE: {directive}\nAVAILABLE ROLES:\n{roster}"
        else:
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

    def heuristic_plan(self, directive: str, role: str) -> Plan:
        """A one-step plan for a plainly simple directive, decided locally with no
        LLM call — the model would only have said "one step" anyway. Signed like
        any plan (marked ``heuristic``) so the trace stays auditable."""
        step = Step(id="s1", role=role, task=directive)
        if self.ledger is not None:
            self.ledger.append(
                self.identity,
                Action.PLAN,
                {"directive": directive, "plan": [step.to_dict()], "heuristic": True},
            )
        return Plan(steps=[step], raw="")
