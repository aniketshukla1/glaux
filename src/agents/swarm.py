"""Swarm orchestrator: router → token-gated delegation → reflect/retry.

The router (also the orchestrator identity that mints capability tokens) plans
a DAG; the swarm executes steps in dependency order, delegating each to its
specialist via a signed capability handoff, and — if a reflector is present —
retries a step (with feedback) until accepted or retries run out. Dependency
outputs are threaded into dependents' context.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from core.ledger import Ledger

from .base import AgentResult, HandoffRejected
from .budget import Budget, BudgetTracker
from .handoff import delegate
from .reflector import Reflector
from .router import Plan, Router, Step


def topo_sort(steps: list[Step]) -> list[Step]:
    """Kahn's algorithm; preserves plan order among ready steps. Raises on cycle."""
    by_id = {s.id: s for s in steps}
    indeg = {s.id: 0 for s in steps}
    adj: dict[str, list[str]] = {s.id: [] for s in steps}
    for s in steps:
        for dep in s.depends_on:
            if dep in by_id:
                adj[dep].append(s.id)
                indeg[s.id] += 1
    queue = deque(s.id for s in steps if indeg[s.id] == 0)
    ordered: list[str] = []
    while queue:
        sid = queue.popleft()
        ordered.append(sid)
        for nxt in adj[sid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if len(ordered) != len(steps):
        raise ValueError("plan has a dependency cycle")
    return [by_id[i] for i in ordered]


@dataclass
class StepResult:
    step: Step
    result: AgentResult
    accepted: bool
    attempts: int


@dataclass
class SwarmResult:
    plan: Plan
    steps: dict = field(default_factory=dict)  # step_id -> StepResult
    final: Optional[str] = None
    success: bool = False
    cost: dict = field(default_factory=dict)
    budget_halt: Optional[str] = None


class Swarm:
    def __init__(
        self,
        *,
        router: Router,
        specialists: dict,
        reflector: Optional[Reflector] = None,
        ledger: Optional[Ledger] = None,
        max_retries: int = 1,
        handoff_ttl: float = 300.0,
    ) -> None:
        self.router = router
        self.specialists = specialists
        self.reflector = reflector
        self.ledger = ledger
        self.max_retries = max_retries
        self.handoff_ttl = handoff_ttl

    def run(
        self,
        directive: str,
        *,
        skills_by_role: Optional[dict] = None,
        budget: Optional[Budget] = None,
    ) -> SwarmResult:
        # One shared budget tracker for the whole task — every LLM caller charges it.
        tracker = BudgetTracker(budget or Budget())
        self.router.budget = tracker
        if self.reflector is not None:
            self.reflector.budget = tracker
        for agent in self.specialists.values():
            agent.budget = tracker

        plan = self.router.plan(directive, roles=list(self.specialists.keys()))
        order = topo_sort(plan.steps)
        results: dict[str, StepResult] = {}
        success = True
        budget_halt: Optional[str] = None

        for step in order:
            # Stop dispatching new work once the task's budget is spent.
            reason = tracker.exceeded()
            if reason is not None:
                budget_halt = reason
                results[step.id] = StepResult(
                    step, AgentResult(False, f"skipped: {reason}", [], 0), False, 0
                )
                success = False
                continue
            target = self.specialists.get(step.role)
            if target is None:
                results[step.id] = StepResult(
                    step, AgentResult(False, f"no specialist for role {step.role!r}", [], 0), False, 0
                )
                success = False
                continue

            context = {
                dep: results[dep].result.result for dep in step.depends_on if dep in results
            }
            skills = (skills_by_role or {}).get(step.role)

            accepted = False
            attempts = 0
            result: Optional[AgentResult] = None
            while attempts <= self.max_retries:
                attempts += 1
                try:
                    result = delegate(
                        self.router.identity,
                        target,
                        step.task,
                        capability=f"task:{step.role}",
                        ledger=self.ledger,
                        ttl=self.handoff_ttl,
                        context=context or None,
                        skills=skills,
                    )
                except HandoffRejected as e:
                    result = AgentResult(False, f"handoff rejected: {e}", [], 0)
                    break

                if self.reflector is None:
                    accepted = result.success
                    break
                verdict = self.reflector.review(step.task, result)
                if verdict.accept:
                    accepted = True
                    break
                # feed the critique back into the next attempt
                context = {**(context or {}), "reflector_feedback": verdict.reason}

            results[step.id] = StepResult(step, result, accepted, attempts)
            if not accepted:
                success = False

        final = results[order[-1].id].result.result if order else None
        return SwarmResult(
            plan=plan,
            steps=results,
            final=final,
            success=success,
            cost=tracker.snapshot(),
            budget_halt=budget_halt,
        )
