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

from core.ledger import Action, Ledger
from llm.gateway import Message

from .base import AgentResult, HandoffRejected
from .budget import Budget, BudgetTracker, charge_for_response
from .handoff import delegate
from .reflector import Reflector
from .router import Plan, Router, Step

FINAL_SYNTH_SYSTEM = (
    "You are the lead of the Athena swarm. Your specialists each completed part of "
    "the user's request. Write the final answer to the ORIGINAL request, integrating "
    "their work into one coherent, complete response that addresses exactly what was "
    "asked. Lead with the answer; do not describe the team or the process."
)


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
    synthesized: list = field(default_factory=list)


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
        synthesizer=None,
        skill_library=None,
        require_approval: bool = False,
    ) -> None:
        self.router = router
        self.specialists = specialists
        self.reflector = reflector
        self.ledger = ledger
        self.max_retries = max_retries
        self.handoff_ttl = handoff_ttl
        self.synthesizer = synthesizer
        self.skill_library = skill_library
        self.require_approval = require_approval

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
        if self.synthesizer is not None:
            self.synthesizer.budget = tracker
        for agent in self.specialists.values():
            agent.budget = tracker

        catalog = {role: getattr(agent, "description", "") for role, agent in self.specialists.items()}
        plan = self.router.plan(directive, roles=list(self.specialists.keys()), role_catalog=catalog)
        order = topo_sort(plan.steps)
        results: dict[str, StepResult] = {}
        success = True
        budget_halt: Optional[str] = None
        synthesized: list = []

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
            verdict = None
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

            # Reflector-triggered autonomous skill synthesis.
            if (
                accepted
                and verdict is not None
                and verdict.synthesize
                and self.synthesizer is not None
                and self.skill_library is not None
            ):
                self._synthesize(verdict.synthesize, synthesized)

        final = self._final_answer(directive, order, results, tracker)
        return SwarmResult(
            plan=plan,
            steps=results,
            final=final,
            success=success,
            cost=tracker.snapshot(),
            budget_halt=budget_halt,
            synthesized=synthesized,
        )

    def _final_answer(self, directive: str, order, results: dict, tracker: BudgetTracker):
        """The swarm's answer to the ORIGINAL directive — not just whatever the last
        step happened to produce. With one step the step's result IS the answer; with
        a team, integrate their outputs so a plan request gets the plan (and not, say,
        the tester's notes because testing ran last)."""
        if not order:
            return None
        done = [results[s.id] for s in order if results[s.id].result and results[s.id].result.result]
        if len(done) <= 1:
            return results[order[-1].id].result.result
        if tracker.exceeded() is not None:  # no budget left to synthesize — use the last output
            return results[order[-1].id].result.result
        return self._synthesize_final(directive, done, tracker)

    def _synthesize_final(self, directive: str, step_results: list, tracker: BudgetTracker):
        parts = [
            f"[{sr.step.role}] {sr.result.result.strip()}"
            for sr in step_results
            if (sr.result.result or "").strip()
        ]
        content = (
            f"ORIGINAL REQUEST: {directive}\n\n"
            "WORK COMPLETED BY YOUR SPECIALISTS:\n" + "\n\n".join(parts) +
            "\n\nWrite the complete final answer to the original request now."
        )
        messages = [Message(role="user", content=content)]
        try:
            resp = self.router.llm.complete(
                messages, system=FINAL_SYNTH_SYSTEM, temperature=0.0, max_tokens=1200
            )
        except Exception:  # noqa: BLE001 - synthesis is best-effort; fall back to last output
            return step_results[-1].result.result
        charge_for_response(tracker, resp, FINAL_SYNTH_SYSTEM, messages)
        if self.ledger is not None:
            self.ledger.append(
                self.router.identity,
                Action.OBSERVATION,
                {"final_synthesis": True, "model_id": resp.model_id},
            )
        return (resp.text or "").strip() or step_results[-1].result.result

    def _synthesize(self, task: str, out: list) -> None:
        """Run the synthesis pipeline for a reflector-recommended skill,
        applying the HITL gate, and log the outcome to the ledger."""
        from skills import PENDING_APPROVAL, is_sensitive  # lazy: keep agents core skills-free

        signer = self.reflector.identity if self.reflector is not None else self.router.identity
        res = self.synthesizer.synthesize(task)
        if self.ledger is not None:
            self.ledger.append(
                signer,
                Action.SYNTHESIZE,
                {
                    "task": task,
                    "ok": res.ok,
                    "reason": res.reason,
                    "skill": res.candidate.name if res.candidate else None,
                },
            )
        if not res.ok:
            out.append({"task": task, "ok": False, "reason": res.reason})
            return

        sensitive = is_sensitive(res.candidate.caps)
        require = self.require_approval or sensitive
        rec = self.skill_library.add_candidate(res.candidate, require_approval=require)
        if rec.status == PENDING_APPROVAL and self.ledger is not None:
            self.ledger.append(
                signer,
                Action.APPROVAL,
                {"skill_id": rec.id, "name": rec.name, "sensitive": sensitive, "caps": rec.caps},
            )
        out.append(
            {"task": task, "ok": True, "skill_id": rec.id, "name": rec.name,
             "status": rec.status, "sensitive": sensitive}
        )
