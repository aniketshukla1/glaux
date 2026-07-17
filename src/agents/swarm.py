"""Swarm orchestrator: router → token-gated delegation → reflect/retry.

The router (also the orchestrator identity that mints capability tokens) plans
a DAG; the swarm executes steps in dependency order, delegating each to its
specialist via a signed capability handoff, and — if a reflector is present —
retries a step (with feedback) until accepted or retries run out. Dependency
outputs are threaded into dependents' context.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from core.ledger import Action, Ledger
from identity.keypair import AgentIdentity
from llm.gateway import Message, stream_complete

from .base import ACTION_INSTRUCTIONS, AgentResult, BaseAgent, HandoffRejected
from .budget import Budget, BudgetTracker, charge_for_response
from .canvas import extract_canvas
from .handoff import delegate
from .tier_router import route_tier
from .reflector import Reflector
from .router import Plan, Router, Step

FINAL_SYNTH_SYSTEM = (
    "You are the lead of the Athena swarm. Your specialists each completed part of "
    "the user's request. Write the final answer to the ORIGINAL request, integrating "
    "their work into one coherent, complete response that addresses exactly what was "
    "asked. Lead with the answer; do not describe the team or the process.\n\n"
    "If a structured view would genuinely help (a comparison, metrics, a breakdown), "
    "you MAY append a Canvas after the prose as a ```canvas fenced JSON block: "
    '{"title": "...", "blocks": [ ... ]}. Allowed blocks: '
    '{"type":"heading","text","level"}, {"type":"text","text"}, '
    '{"type":"metric","items":[{"label","value","delta"}]}, '
    '{"type":"table","columns":[...],"rows":[[...]]}, '
    '{"type":"list","items":[...],"ordered":bool}, {"type":"code","language","code"}, '
    '{"type":"callout","tone":"info|success|warn|danger","text"}, '
    '{"type":"chart","kind":"bar|line","labels":[...],"series":[{"name","data":[...]}]}, '
    '{"type":"divider"}. Only include a Canvas when it adds real value; otherwise omit it.'
)


_RESPONDER_SYSTEM = (
    "You are Athena, answering the user directly. Give a correct, concise answer from "
    "your own knowledge — do NOT call tools or skills, and do not deliberate. Reply with "
    'a single JSON object in a ```json block: {"action": "finish", "result": "<your full '
    'answer>", "success": true}.'
)

# The medium-tier generalist: one capable agent that finishes the whole task itself.
GENERALIST_SYSTEM = (
    "You are Athena, a capable generalist agent. Complete the user's task end to end "
    "yourself: reason about it, use available skills and tools when they genuinely help, "
    "then finish with a complete, correct answer. Prefer the fewest steps that do the job, "
    "and batch independent tool calls into one step. If the answer needs an exact "
    "computation you cannot do reliably from memory (hashes, checksums, big-number math, "
    "encodings, parsing), use a tool. To create, read, or edit FILES, use the write_file / "
    "read_file / list_files tools when available — never create_skill for file operations. "
    "create_skill is ONLY for a missing computation/logic tool: if no available tool fits, "
    "do NOT keep retrying one that doesn't — create a purpose-built one, then call it.\n"
    + ACTION_INSTRUCTIONS
)


def _is_live(llm) -> bool:
    """True for a real model backend. The demo backend is instant, so the fast
    path gives it nothing and would only reshape the demo's multi-agent trace."""
    return getattr(llm, "model_id", "") not in ("", "demo-offline")


def _as_text(value) -> str:
    """A step result may be a string, a dict/list (model returned structured JSON),
    or None. Coerce to readable text so synthesis and display never choke on it."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


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


def dependency_levels(steps: list[Step]) -> list[list[Step]]:
    """Group steps into dependency levels: every step in a level depends only on
    steps in earlier levels, so a level's steps are mutually independent and can
    run concurrently. Preserves plan order within a level. Raises on a cycle."""
    by_id = {s.id: s for s in steps}
    depth: dict[str, int] = {}
    for s in topo_sort(steps):  # also enforces acyclicity
        deps = [d for d in s.depends_on if d in by_id]
        depth[s.id] = 1 + max((depth[d] for d in deps), default=-1)
    groups: dict[int, list[Step]] = defaultdict(list)
    for s in steps:  # plan order within each level
        groups[depth[s.id]].append(s)
    return [groups[k] for k in sorted(groups)]


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
    cancelled: bool = False
    canvas: Optional[dict] = None  # generative UI spec extracted from the answer
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
        fast_replies: bool = True,
        responder=None,
        max_parallel: int = 8,
        synthesis_llm=None,
        generalist=None,
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
        # Answer plainly-simple queries in a single call (skip planning + reflection).
        self.fast_replies = fast_replies
        self._responder = responder  # lean, tool-free agent for the fast path
        self.max_parallel = max_parallel  # concurrency cap for independent branches
        # The user-facing final answer uses the primary model even under tiering
        # (routing/reflection may run on a cheap model, but the deliverable shouldn't).
        self._synthesis_llm = synthesis_llm
        # Medium tier: one capable tool-using agent for non-trivial-but-single-focus
        # tasks — no planning call, no reflector. None -> fall through to the swarm.
        self.generalist = generalist

    def _answerer_role(self) -> Optional[str]:
        for pref in ("researcher", "writer", "analyst"):
            if pref in self.specialists:
                return pref
        return next(iter(self.specialists), None)

    def _responder_agent(self) -> BaseAgent:
        """A lean answerer for the fast path: no tools, no skills, one shot. The
        specialists carry tool-use scaffolding that makes them fumble (and loop on)
        a trivial question; this one just answers and finishes."""
        if self._responder is None:
            self._responder = BaseAgent(
                identity=AgentIdentity.generate(),
                llm=self.router.llm,
                ledger=self.ledger,
                name="responder",
                system_prompt=_RESPONDER_SYSTEM,
                max_iterations=2,
                mcp_client=None,
            )
        return self._responder

    def _run_step(self, step, target, context, skills, step_reflector, cancel):
        """Run one plan step: delegate under a capability token, then reflect/retry
        until accepted or retries run out. Returns (StepResult, verdict). Safe to
        call from a worker thread — ledger/budget writes serialize themselves."""
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
                    cancel=cancel,
                )
            except HandoffRejected as e:
                result = AgentResult(False, f"handoff rejected: {e}", [], 0)
                break
            if step_reflector is None:
                accepted = result.success
                break
            verdict = step_reflector.review(step.task, result)
            if verdict.accept:
                accepted = True
                break
            # feed the critique back into the next attempt
            context = {**(context or {}), "reflector_feedback": verdict.reason}
        return StepResult(step, result, accepted, attempts), verdict

    def run(
        self,
        directive: str,
        *,
        skills_by_role: Optional[dict] = None,
        budget: Optional[Budget] = None,
        cancel=None,
        on_token=None,
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

        # Fast path: a plainly-simple query gets one direct answer — skip the
        # router's planning call and the reflector (both are pure latency here).
        # Three tiers, cheapest first — both shortcuts skip the router-planning call
        # and the reflector, and route the one step to a single agent instead of a team.
        # The tier is chosen by an embedding classifier (keyword fallback) on the text.
        answerer = self._answerer_role()
        live = self.fast_replies and _is_live(self.router.llm)
        content_tier = route_tier(directive) if live else "full"
        fast = live and answerer is not None and content_tier == "fast"
        medium = (not fast) and live and self.generalist is not None and content_tier == "medium"

        single_agent = None   # responder (fast) or generalist (medium); None for the swarm
        single_skills = None  # skills override for the single agent
        if fast:
            plan = self.router.heuristic_plan(directive, answerer)
            step_reflector = None
            single_agent = self._responder_agent()
            single_skills = {}  # tool-free: answer from own knowledge
        elif medium:
            plan = self.router.heuristic_plan(directive, "generalist")
            step_reflector = None
            single_agent = self.generalist
            single_skills = None  # the agent uses its own tools + retrieved skills
        else:
            catalog = {role: getattr(agent, "description", "") for role, agent in self.specialists.items()}
            plan = self.router.plan(directive, roles=list(self.specialists.keys()), role_catalog=catalog)
            step_reflector = self.reflector
        if single_agent is not None:
            single_agent.budget = tracker
        order = topo_sort(plan.steps)
        levels = dependency_levels(plan.steps)
        results: dict[str, StepResult] = {}
        success = True
        budget_halt: Optional[str] = None
        cancelled = False
        synthesized: list = []

        # Execute level by level. Steps within a level are independent (they only
        # depend on earlier levels), so we run them concurrently; the ledger and
        # budget tracker serialize their own writes.
        for level in levels:
            if cancel is not None and cancel():
                cancelled = True
                success = False
                break
            reason = tracker.exceeded()
            if reason is not None:
                budget_halt = reason
                for step in level:
                    results[step.id] = StepResult(
                        step, AgentResult(False, f"skipped: {reason}", [], 0), False, 0
                    )
                success = False
                break

            runnable = []
            for step in level:
                target = single_agent if single_agent is not None else self.specialists.get(step.role)
                if target is None:
                    results[step.id] = StepResult(
                        step, AgentResult(False, f"no specialist for role {step.role!r}", [], 0), False, 0
                    )
                    success = False
                    continue
                context = {
                    dep: results[dep].result.result for dep in step.depends_on if dep in results
                }
                skills = single_skills if single_agent is not None else (skills_by_role or {}).get(step.role)
                runnable.append((step, target, context, skills))

            level_out: list = []  # (StepResult, verdict)
            if len(runnable) == 1:
                level_out.append(self._run_step(*runnable[0], step_reflector, cancel))
            elif runnable:
                workers = min(len(runnable), self.max_parallel)
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="swarm") as ex:
                    futs = [
                        ex.submit(self._run_step, step, target, context, skills, step_reflector, cancel)
                        for step, target, context, skills in runnable
                    ]
                    for fut in as_completed(futs):
                        level_out.append(fut.result())

            # Fold results back on the main thread (order-independent), then run any
            # reflector-triggered synthesis serially (it mutates the skill library).
            for sr, verdict in level_out:
                results[sr.step.id] = sr
                if not sr.accepted:
                    success = False
                if (
                    sr.accepted and verdict is not None and verdict.synthesize
                    and self.synthesizer is not None and self.skill_library is not None
                ):
                    self._synthesize(verdict.synthesize, synthesized)

        if cancelled:
            done = [_as_text(results[s.id].result.result) for s in order
                    if s.id in results and results[s.id].result and results[s.id].result.result]
            final = (done[-1] if done else None) or "Stopped."
        else:
            # Synthesis is presentation-only: it must never turn a completed run into a
            # failure, so any error here falls back to the last step's output.
            try:
                final = self._final_answer(directive, order, results, tracker, on_token=on_token)
            except Exception:  # noqa: BLE001
                final = _as_text(results[order[-1].id].result.result) if order else None
        # A model may render a structured Canvas (A2UI) alongside the prose answer.
        final, canvas = extract_canvas(final)
        return SwarmResult(
            plan=plan,
            steps=results,
            final=final,
            success=success,
            cost=tracker.snapshot(),
            budget_halt=budget_halt,
            cancelled=cancelled,
            canvas=canvas,
            synthesized=synthesized,
        )

    def _final_answer(self, directive: str, order, results: dict, tracker: BudgetTracker, on_token=None):
        """The swarm's answer to the ORIGINAL directive — not just whatever the last
        step happened to produce. With one step the step's result IS the answer; with
        a team, integrate their outputs so a plan request gets the plan (and not, say,
        the tester's notes because testing ran last)."""
        if not order:
            return None
        last = _as_text(results[order[-1].id].result.result)
        done = [results[s.id] for s in order if results[s.id].result and _as_text(results[s.id].result.result).strip()]
        if len(done) <= 1:
            return last
        if tracker.exceeded() is not None:  # no budget left to synthesize — use the last output
            return last
        return self._synthesize_final(directive, done, tracker, on_token=on_token)

    def _synthesize_final(self, directive: str, step_results: list, tracker: BudgetTracker, on_token=None):
        parts = []
        for sr in step_results:
            text = _as_text(sr.result.result).strip()
            if text:
                parts.append(f"[{sr.step.role}] {text}")
        content = (
            f"ORIGINAL REQUEST: {directive}\n\n"
            "WORK COMPLETED BY YOUR SPECIALISTS:\n" + "\n\n".join(parts) +
            "\n\nWrite the complete final answer to the original request now."
        )
        messages = [Message(role="user", content=content)]
        synth_llm = self._synthesis_llm or self.router.llm
        try:
            # Stream the final answer when a token sink is wired (so the UI types it
            # out); falls back to a single call otherwise.
            resp = stream_complete(
                synth_llm, messages, on_delta=on_token,
                system=FINAL_SYNTH_SYSTEM, temperature=0.0, max_tokens=1200,
            )
        except Exception:  # noqa: BLE001 - synthesis is best-effort; fall back to last output
            return _as_text(step_results[-1].result.result)
        charge_for_response(tracker, resp, FINAL_SYNTH_SYSTEM, messages)
        if self.ledger is not None:
            self.ledger.append(
                self.router.identity,
                Action.OBSERVATION,
                {"final_synthesis": True, "model_id": resp.model_id},
            )
        return (resp.text or "").strip() or _as_text(step_results[-1].result.result)

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
