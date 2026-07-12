"""BaseAgent: the signed, sandboxed ReAct loop.

Each agent is a cryptographic identity. Every reasoning step, skill call, and
observation is signed onto the swarm ledger. Skills execute in the Phase 0
sandbox under their declared capabilities. The loop honors the global kill
switch, checkpoints its state after every step (durable/resumable execution),
and records a reproducibility envelope (model, temperature, seed, prompt
hashes) so a regression in this self-improving system is debuggable.

Skill code is fetched from procedural memory (or supplied directly) and offered
to the model; the model invokes by id. Cross-agent handoff (`call_agent`) is
defined here but wired up with the swarm in Phase 3.2.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import safety
from core.ledger import Action, Ledger
from identity import verify_token
from identity.keypair import AgentIdentity
from llm.gateway import LLMClient, Message
from sandbox import Capabilities, SecretsBroker, run as sandbox_run

from .budget import BudgetTracker, charge_for_response
from .protocol import CALL_AGENT, CALL_MCP, CALL_SKILL, CREATE_SKILL, FINISH, parse_actions

ACTION_INSTRUCTIONS = """Reason step by step about the goal, then emit an action as a JSON object in a ```json code block. Available actions:
- {"action": "call_skill", "skill_id": "<id>", "args": {...}} — run a skill from your library.
- {"action": "call_mcp", "tool": "<name>", "args": {...}} — call an external MCP tool.
- {"action": "finish", "result": "<answer>", "success": true} — complete the task.
To run several INDEPENDENT tool calls at once (they don't depend on each other's
results), batch them: {"actions": [ {...}, {...} ]} — they execute in parallel.
Only call skills/tools that are listed as available — never invent an id. If no
skill or tool fits, just answer directly and finish. Do not repeat an action that
already failed. Keep all args JSON-serializable."""

DEFAULT_ROLE = "You are {name}, a specialist agent in the Athena swarm."


class HandoffRejected(Exception):
    """Raised when an agent refuses a handoff (invalid/expired/misaddressed token)."""


@dataclass
class AgentResult:
    success: bool
    result: Optional[str]
    steps: list[dict]
    iterations: int
    halted: bool = False
    reproducibility: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)


def _caps_from_dict(d: dict) -> Capabilities:
    return Capabilities.from_dict(d)


def _hash_prompt(system: Optional[str], messages: list[Message]) -> str:
    h = hashlib.sha256()
    h.update((system or "").encode("utf-8"))
    for m in messages:
        h.update(b"\x00")
        h.update(m.role.encode("utf-8"))
        h.update(b"\x01")
        h.update(m.content.encode("utf-8"))
    return h.hexdigest()


class BaseAgent:
    def __init__(
        self,
        *,
        identity: AgentIdentity,
        llm: LLMClient,
        ledger: Optional[Ledger] = None,
        memory=None,
        secrets_broker: Optional[SecretsBroker] = None,
        name: str = "agent",
        system_prompt: Optional[str] = None,
        max_iterations: int = 8,
        max_repeats: int = 3,
        temperature: float = 0.0,
        seed: Optional[int] = None,
        max_tokens: int = 1024,
        checkpoint_dir: Optional[str] = None,
        budget: Optional[BudgetTracker] = None,
        mcp_client=None,
        synthesizer=None,
        skill_library=None,
    ) -> None:
        self.identity = identity
        self.llm = llm
        self.ledger = ledger
        self.memory = memory
        self.secrets_broker = secrets_broker
        self.budget = budget
        self.mcp_client = mcp_client
        # On-the-fly tool creation: when set, the agent can synthesize a new skill
        # mid-task (sandbox-tested) and call it in the same run.
        self.synthesizer = synthesizer
        self.skill_library = skill_library
        self.name = name
        # A provided prompt is used verbatim (so specialists can include their
        # own JSON examples without str.format choking on the braces).
        self.system_prompt = (
            system_prompt
            if system_prompt is not None
            else DEFAULT_ROLE.format(name=name) + "\n" + ACTION_INSTRUCTIONS
        )
        self.max_iterations = max_iterations
        self.max_repeats = max_repeats
        self.temperature = temperature
        self.seed = seed
        self.max_tokens = max_tokens
        self.checkpoint_dir = checkpoint_dir

    # --- public ----------------------------------------------------------

    def accept_handoff(
        self,
        token,
        issuer_public_key_b58: str,
        goal: str,
        *,
        capability: Optional[str] = None,
        **run_kwargs,
    ) -> "AgentResult":
        """Accept a delegated task only if `token` is a valid capability grant
        issued *to this agent* by `issuer_public_key_b58`. Receiver-side check —
        this is where the Phase 0 capability tokens are enforced."""
        if not verify_token(
            token, issuer_public_key_b58, subject=self.identity.agent_id, capability=capability
        ):
            raise HandoffRejected(
                f"{self.name} rejected handoff: capability token invalid, expired, "
                f"or not issued to this agent"
            )
        return self.run(goal, **run_kwargs)

    def run(
        self,
        goal: str,
        *,
        task_id: Optional[str] = None,
        context: Optional[dict] = None,
        skills: Optional[dict] = None,
        resume: bool = False,
        cancel=None,
    ) -> AgentResult:
        task_id = task_id or uuid.uuid4().hex

        if safety.is_halted():
            return AgentResult(False, "execution halted by kill switch", [], 0, halted=True)

        state = self._load_checkpoint(task_id) if (resume and self.checkpoint_dir) else None
        scratchpad: list[dict] = state["scratchpad"] if state else []
        start_iter = state["iteration"] if state else 0

        available = skills if skills is not None else self._retrieve_skills(goal)
        repro = {
            "model_id": getattr(self.llm, "model_id", "unknown"),
            "temperature": self.temperature,
            "seed": self.seed,
            "prompt_hashes": [],
            "skills_offered": sorted(available.keys()),
        }
        repeats: dict[str, int] = {}

        for i in range(start_iter, self.max_iterations):
            # User-requested stop: bail out cleanly before spending more.
            if cancel is not None and cancel():
                self._log(Action.OBSERVATION, {"aborted": True, "reason": "stopped by user"})
                return AgentResult(
                    False, "stopped by user", scratchpad, i,
                    reproducibility=repro, cost=self._cost(),
                )
            # Cost/budget guard: stop cleanly *before* spending more.
            if self.budget is not None:
                reason = self.budget.exceeded()
                if reason is not None:
                    self._log(Action.OBSERVATION, {"budget_halt": True, "reason": reason})
                    return AgentResult(
                        False, f"halted: {reason}", scratchpad, i,
                        reproducibility=repro, cost=self._cost(),
                    )

            messages = self._build_messages(goal, scratchpad, available, context)
            prompt_hash = _hash_prompt(self.system_prompt, messages)
            repro["prompt_hashes"].append(prompt_hash)

            resp = self.llm.complete(
                messages,
                system=self.system_prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                seed=self.seed,
            )
            charge_for_response(self.budget, resp, self.system_prompt, messages)
            actions = parse_actions(resp.text)
            self._log(
                Action.THINK,
                {"thought": resp.text[:2000], "prompt_hash": prompt_hash, "model_id": resp.model_id},
            )
            step: dict = {"iteration": i, "thought": resp.text, "actions": actions, "observations": []}
            scratchpad.append(step)

            # finish is terminal — honor it even if the model batched it with tools.
            finish = next((a for a in actions if a.get("action") == FINISH), None)
            if finish is not None:
                self._log(Action.OBSERVATION, {"finish": True, "result": finish.get("result")})
                self._save_checkpoint(task_id, scratchpad, i + 1, goal)
                return AgentResult(
                    success=bool(finish.get("success", True)),
                    result=finish.get("result"),
                    steps=scratchpad,
                    iterations=i + 1,
                    reproducibility=repro,
                    cost=self._cost(),
                )

            tool_actions = [a for a in actions if a.get("action") != FINISH]
            if not tool_actions:
                observations = [{"error": "no valid JSON action parsed"}]
            elif len(tool_actions) == 1:
                observations = [self._execute_action(tool_actions[0], available)]
            else:
                # Independent tool calls in one turn run concurrently (ledger and
                # budget serialize their own writes).
                workers = min(len(tool_actions), 8)
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tools") as ex:
                    observations = list(ex.map(lambda a: self._execute_action(a, available), tool_actions))
            step["observations"] = observations

            # Loop guard: abort if the agent keeps repeating a non-progressing turn
            # (e.g. calling a skill that doesn't exist). A batch progresses if any of
            # its tool calls succeeded. Prevents models burning iterations on a loop.
            progressed = any(isinstance(o, dict) and o.get("ok") for o in observations)
            if not progressed:
                sig = "|".join(self._action_signature(a) for a in tool_actions) or "none"
                repeats[sig] = repeats.get(sig, 0) + 1
                if repeats[sig] >= self.max_repeats:
                    self._log(
                        Action.OBSERVATION,
                        {"aborted": True, "reason": f"repeated {sig!r} {repeats[sig]}x"},
                    )
                    return AgentResult(
                        False,
                        f"aborted: repeated a non-progressing action ({sig}) {repeats[sig]} times",
                        scratchpad,
                        i + 1,
                        reproducibility=repro,
                        cost=self._cost(),
                    )

            self._save_checkpoint(task_id, scratchpad, i + 1, goal)

        return AgentResult(
            False, "max iterations reached", scratchpad, self.max_iterations,
            reproducibility=repro, cost=self._cost(),
        )

    # --- internals -------------------------------------------------------

    def _cost(self) -> dict:
        return self.budget.snapshot() if self.budget is not None else {}

    @staticmethod
    def _action_signature(action: Optional[dict]) -> str:
        if not action:
            return "no_action"
        atype = action.get("action")
        if atype == CALL_SKILL:
            return f"call_skill:{action.get('skill_id')}"
        if atype == CALL_MCP:
            return f"call_mcp:{action.get('tool')}"
        if atype == CREATE_SKILL:
            return f"create_skill:{action.get('name') or (action.get('task') or '')[:24]}"
        return str(atype)

    def _create_skill(self, action: dict, available: dict) -> dict:
        """On-the-fly tool creation. When no existing skill/tool fits, the agent
        describes what it needs; Athena synthesizes the code, static-cap-checks it,
        runs its auto-generated tests in the sandbox, and — if they pass — adds it
        to this run's skills so the agent can call_skill it next. Signed to the
        ledger, so the whole creation is auditable."""
        if self.synthesizer is None:
            return {"ok": False, "error": "tool creation is not enabled for this agent"}
        task = (action.get("task") or action.get("description") or "").strip()
        if not task:
            return {"ok": False, "error": "create_skill needs a 'task' describing what the tool should do"}
        self.synthesizer.budget = self.budget  # charge the same task budget
        res = self.synthesizer.synthesize(task)
        cand = res.candidate
        if not res.ok or cand is None:
            return {
                "ok": False,
                "error": f"tool synthesis failed: {res.reason}",
                "cap_violations": res.cap_violations,
                "failed_tests": [t.get("error") for t in res.test_results if not t.get("ok")][:3],
            }
        sid = str(action.get("name") or cand.name)
        available[sid] = {
            "code": cand.code, "caps": cand.caps, "entrypoint": cand.entrypoint,
            "name": cand.name, "description": cand.description,
        }
        if self.skill_library is not None:
            try:
                self.skill_library.add_candidate(cand)  # persist for reuse
            except Exception:  # noqa: BLE001 - persistence is best-effort
                pass
        self._log(Action.SYNTHESIZE, {
            "name": sid, "description": cand.description,
            "entrypoint": cand.entrypoint, "tests_passed": True, "on_the_fly": True,
        })
        return {
            "ok": True, "created": sid, "entrypoint": cand.entrypoint,
            "description": cand.description,
            "message": f"tool {sid!r} created and sandbox-tested — call it with call_skill next.",
        }

    def _execute_action(self, action: dict, available: dict) -> dict:
        """Run one tool action, log its CALL + OBSERVATION, return the observation.
        Never raises — a tool's failure becomes an error observation so its batch
        mates can still succeed (called concurrently for batched tool calls)."""
        atype = action.get("action")
        try:
            if atype == CALL_SKILL:
                self._log(Action.CALL_SKILL, {"skill_id": action.get("skill_id"), "args": action.get("args")})
                obs = self._run_skill(available, action)
                self._log(Action.OBSERVATION, {"skill_id": action.get("skill_id"), "ok": obs.get("ok"), "error": obs.get("error")})
                return obs
            if atype == CREATE_SKILL:
                return self._create_skill(action, available)
            if atype == CALL_MCP:
                obs = self._call_mcp(action)
                self._log(Action.MCP_TOOL, {"tool": action.get("tool"), "args": action.get("args"), "ok": obs.get("ok")})
                if not obs.get("ok") and self.synthesizer is not None:
                    obs["hint"] = ("this tool did not do it — do NOT retry it; if no available "
                                   "tool fits, create one with create_skill")
                return obs
            if atype == CALL_AGENT:
                self._log(Action.CALL_AGENT, {"target": action.get("agent_id")})
                return {"error": "agent handoff not available in single-agent runtime (Phase 3.2)"}
            return {"error": f"unknown action {atype!r}"}
        except Exception as e:  # noqa: BLE001 - one tool's failure must not sink the batch
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def _run_skill(self, available: dict, action: dict) -> dict:
        skill_id = action.get("skill_id")
        skill = available.get(skill_id)
        if not skill:
            avail = list(available.keys())
            hint = (
                f" Available skills: {avail}."
                if avail
                else " No skills are available — answer the task yourself and finish."
            )
            return {"ok": False, "error": f"unknown skill {skill_id!r}.{hint}"}
        caps = _caps_from_dict(skill.get("caps") or {})
        res = sandbox_run(
            skill["code"],
            caps=caps,
            inputs=action.get("args") or {},
            entrypoint=skill.get("entrypoint", "run"),
            broker=self.secrets_broker,
        )
        return {
            "ok": res.ok,
            "return_value": res.return_value,
            "stdout": res.stdout,
            "error": res.error,
            "killed_reason": res.killed_reason,
        }

    def _call_mcp(self, action: dict) -> dict:
        if self.mcp_client is None:
            return {"ok": False, "error": "no MCP client configured"}
        if safety.is_dry_run():
            return {"ok": True, "result": "[dry-run] MCP call skipped"}
        return self.mcp_client.call_tool(action.get("tool"), action.get("args") or {})

    def _retrieve_skills(self, goal: str) -> dict:
        if self.memory is None:
            return {}
        hits = self.memory.procedural.search(goal, k=5)
        skills = {}
        for h in hits:
            meta = h.metadata
            skills[h.id] = {
                "code": meta.get("code", ""),
                "caps": meta.get("caps", {}),
                "name": meta.get("name", h.id),
                "description": meta.get("description"),
                "entrypoint": meta.get("entrypoint", "run"),
            }
        return skills

    def _build_messages(
        self, goal: str, scratchpad: list[dict], available: dict, context: Optional[dict]
    ) -> list[Message]:
        lines = [f"GOAL: {goal}"]
        if context:
            lines.append(f"CONTEXT: {json.dumps(context)}")
        if available:
            lines.append("AVAILABLE SKILLS:")
            for sid, s in available.items():
                lines.append(f"- {sid}: {s.get('name', sid)} — {s.get('description') or ''}")
        else:
            lines.append("AVAILABLE SKILLS: none (do not use call_skill)")
        if self.mcp_client is not None:
            tools = self.mcp_client.list_tools()
            if tools:
                lines.append("AVAILABLE MCP TOOLS:")
                for t in tools:
                    lines.append(f"- {t.name}: {t.description} args={t.input_schema}")
        if self.synthesizer is not None:
            lines.append(
                'If NO available skill or tool does what you need, CREATE one: '
                '{"action": "create_skill", "name": "<id>", "task": "<precise description of the '
                'tool: inputs, output, behavior>"} — Athena writes it, sandbox-tests it, and adds '
                'it so you can call_skill it on the next step.'
            )
        if scratchpad:
            lines.append("HISTORY:")
            for step in scratchpad:
                lines.append(f"[{step['iteration']}] thought: {step['thought'][:500]}")
                obs_list = step.get("observations")
                if obs_list is None and step.get("observation") is not None:
                    obs_list = [step["observation"]]  # resumed pre-batch checkpoint
                for obs in obs_list or []:
                    lines.append(f"    observation: {json.dumps(obs)[:500]}")
        lines.append(
            "Respond with your reasoning, then a JSON action block "
            '(or {"actions": [ ... ]} to run independent tool calls in parallel).'
        )
        return [Message(role="user", content="\n".join(lines))]

    def _log(self, action_type: str, payload: dict) -> None:
        if self.ledger is not None:
            self.ledger.append(self.identity, action_type, payload)

    # --- checkpointing ---------------------------------------------------

    def _checkpoint_path(self, task_id: str) -> Path:
        return Path(self.checkpoint_dir) / f"{task_id}.json"

    def _save_checkpoint(self, task_id: str, scratchpad: list[dict], iteration: int, goal: str) -> None:
        if not self.checkpoint_dir:
            return
        Path(self.checkpoint_dir).mkdir(parents=True, exist_ok=True)
        path = self._checkpoint_path(task_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"goal": goal, "scratchpad": scratchpad, "iteration": iteration}))
        os.replace(tmp, path)

    def _load_checkpoint(self, task_id: str) -> Optional[dict]:
        path = self._checkpoint_path(task_id)
        if path.exists():
            return json.loads(path.read_text())
        return None
