"""Reflector: reviews a specialist's result and decides accept vs. retry.

This is the upgrade from a bare "evaluator" — it can *reject and retry* (the
swarm re-runs the step with the reflector's feedback in context), not merely
log. Skill synthesis on the back of a reflection lands in Phase 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.ledger import Action, Ledger
from identity.keypair import AgentIdentity
from llm.gateway import LLMClient, Message

from .protocol import extract_json

REFLECTOR_SYSTEM = """You review whether a specialist agent's result satisfies its
task. Respond with a single JSON object in a ```json block:
{"verdict": "accept" | "retry", "reason": "<short justification>"}
Use "retry" only if the result is wrong, incomplete, or unsafe."""


@dataclass
class Verdict:
    accept: bool
    reason: str = ""
    raw: str = ""


class Reflector:
    def __init__(
        self,
        *,
        identity: AgentIdentity,
        llm: LLMClient,
        ledger: Optional[Ledger] = None,
        name: str = "reflector",
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> None:
        self.identity = identity
        self.llm = llm
        self.ledger = ledger
        self.name = name
        self.temperature = temperature
        self.max_tokens = max_tokens

    def review(self, goal: str, result) -> Verdict:
        summary = {
            "success": result.success,
            "result": result.result,
            "iterations": result.iterations,
        }
        content = f"TASK: {goal}\nRESULT: {summary}"
        resp = self.llm.complete(
            [Message(role="user", content=content)],
            system=REFLECTOR_SYSTEM,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        data = extract_json(resp.text) or {}
        verdict = str(data.get("verdict", "accept")).lower()
        accept = verdict == "accept"
        reason = str(data.get("reason", ""))
        if self.ledger is not None:
            self.ledger.append(
                self.identity,
                Action.REFLECT,
                {"goal": goal, "verdict": verdict, "reason": reason},
            )
        return Verdict(accept=accept, reason=reason, raw=resp.text)
