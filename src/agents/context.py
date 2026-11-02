"""Long-horizon context management: keep the prompt bounded on long runs.

A ReAct agent's message history grows with every step. Left unchecked it blows
the model's context window — and inflates latency and cost — on long tasks. This
compacts the HISTORY section under a fixed character budget: the most recent
steps are kept verbatim, older ones collapse to one-line digests, and anything
that still doesn't fit is elided with a count. Deterministic by default (no extra
LLM call, so it doesn't add latency); an optional ``summarize`` hook can fold the
elided steps into a prose summary when fidelity matters more than speed.

This is Glaux's answer to deepagents' SummarizationMiddleware — but budget-first
and deterministic, and every compaction is signed to the ledger.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable, Optional

from .protocol import CALL_AGENT, CALL_MCP, CALL_SKILL, CREATE_SKILL, FINISH


@dataclass
class CompactionStats:
    """What the last render kept, digested, or dropped — for the ledger + UI."""

    total_steps: int = 0
    verbatim: int = 0
    digested: int = 0
    elided: int = 0
    chars: int = 0

    @property
    def compacted(self) -> bool:
        return self.digested > 0 or self.elided > 0

    def to_dict(self) -> dict:
        return {
            "total_steps": self.total_steps,
            "verbatim": self.verbatim,
            "digested": self.digested,
            "elided": self.elided,
            "chars": self.chars,
            "compacted": self.compacted,
        }


def _clip(s, n: int) -> str:
    s = s if isinstance(s, str) else str(s)
    if len(s) <= n:
        return s
    return s[:n] + f"…(+{len(s) - n} chars)"


class ContextManager:
    """Bounds the rendered HISTORY to a character budget, newest-first.

    Recent steps are shown verbatim (up to ``keep_recent_steps`` and a fraction
    of the budget); everything older degrades to compact one-line digests; the
    remainder is elided (or summarized, if a ``summarize`` hook is supplied).
    """

    def __init__(
        self,
        *,
        max_history_chars: int = 6000,
        keep_recent_steps: int = 3,
        thought_chars: int = 500,
        obs_chars: int = 400,
        summarize: Optional[Callable[[list[dict]], str]] = None,
    ) -> None:
        self.max_history_chars = max(500, int(max_history_chars))
        self.keep_recent_steps = max(1, int(keep_recent_steps))
        self.thought_chars = max(0, int(thought_chars))
        self.obs_chars = max(0, int(obs_chars))
        self.summarize = summarize
        self.last_stats = CompactionStats()

    @classmethod
    def from_env(cls, **overrides) -> "ContextManager":
        def _int(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, default))
            except (TypeError, ValueError):
                return default

        params = dict(
            max_history_chars=_int("GLAUX_CONTEXT_MAX_CHARS", 6000),
            keep_recent_steps=_int("GLAUX_CONTEXT_KEEP_RECENT", 3),
            thought_chars=_int("GLAUX_CONTEXT_THOUGHT_CHARS", 500),
            obs_chars=_int("GLAUX_CONTEXT_OBS_CHARS", 400),
        )
        params.update(overrides)
        return cls(**params)

    def config(self) -> dict:
        return {
            "max_history_chars": self.max_history_chars,
            "keep_recent_steps": self.keep_recent_steps,
            "thought_chars": self.thought_chars,
            "obs_chars": self.obs_chars,
            "summarize": self.summarize is not None,
        }

    # --- rendering -------------------------------------------------------

    def render_history(self, scratchpad: list[dict]) -> tuple[list[str], CompactionStats]:
        """Return the HISTORY lines (chronological) and the compaction stats.

        Walks newest → oldest so recent context always survives the budget; older
        steps fall back to digests, then to an elided count once the budget is
        spent. The returned lines never exceed ``max_history_chars`` in total.
        """
        if not scratchpad:
            self.last_stats = CompactionStats()
            return [], self.last_stats

        budget = self.max_history_chars
        verbatim_budget = int(budget * 0.6)
        chosen: list[tuple[int, str]] = []
        used = verbatim_used = n_verbatim = n_digest = 0

        for idx in range(len(scratchpad) - 1, -1, -1):
            step = scratchpad[idx]
            block = self._verbatim(step)
            if (
                n_verbatim < self.keep_recent_steps
                and verbatim_used + len(block) <= verbatim_budget
                and used + len(block) <= budget
            ):
                chosen.append((idx, block))
                used += len(block)
                verbatim_used += len(block)
                n_verbatim += 1
                continue
            digest = self._digest(step)
            if used + len(digest) <= budget:
                chosen.append((idx, digest))
                used += len(digest)
                n_digest += 1
            else:
                # Budget spent — everything older is "earlier" and is elided,
                # so stop here to keep the surviving block contiguous + ordered.
                break

        elided = len(scratchpad) - len(chosen)
        chosen.sort(key=lambda t: t[0])  # back to chronological order

        lines = ["HISTORY:"]
        if elided > 0:
            summary = None
            if self.summarize is not None:
                try:
                    summary = self.summarize(scratchpad[:elided])
                except Exception:  # noqa: BLE001 - summary is best-effort
                    summary = None
            if summary:
                lines.append(f"    earlier progress (summarized): {_clip(summary, 800)}")
            else:
                lines.append(f"    (… {elided} earlier step(s) elided to fit the context budget)")
        lines.extend(text for _idx, text in chosen)

        self.last_stats = CompactionStats(
            total_steps=len(scratchpad),
            verbatim=n_verbatim,
            digested=n_digest,
            elided=elided,
            chars=used,
        )
        return lines, self.last_stats

    # --- step rendering --------------------------------------------------

    def _verbatim(self, step: dict) -> str:
        it = step.get("iteration", "?")
        parts = [f"[{it}] thought: {_clip(step.get('thought', ''), self.thought_chars)}"]
        for obs in self._observations(step):
            parts.append(f"    observation: {_clip(self._obs_text(obs), self.obs_chars)}")
        return "\n".join(parts)

    def _digest(self, step: dict) -> str:
        it = step.get("iteration", "?")
        head = _clip(" ".join((step.get("thought") or "").split()), 100)
        sigs = ", ".join(self._sig(a) for a in (step.get("actions") or [])) or "no-op"
        obs = self._observations(step)
        tail = ""
        if obs:
            ok = sum(1 for o in obs if isinstance(o, dict) and o.get("ok"))
            tail = f" [{ok}/{len(obs)} ok]"
            err = next((o.get("error") for o in obs if isinstance(o, dict) and o.get("error")), None)
            if err:
                tail += f" err: {_clip(str(err), 80)}"
        return f"[{it}] {head} → {sigs}{tail}"

    @staticmethod
    def _observations(step: dict) -> list:
        obs = step.get("observations")
        if obs is None and step.get("observation") is not None:
            return [step["observation"]]  # legacy / pre-batch checkpoint
        return obs or []

    @staticmethod
    def _obs_text(obs) -> str:
        if isinstance(obs, dict) and ("return_value" in obs or "ok" in obs):
            view = {
                k: obs[k]
                for k in ("ok", "return_value", "error", "created", "result", "path")
                if k in obs
            }
            return json.dumps(view, default=str)
        return json.dumps(obs, default=str)

    @staticmethod
    def _sig(action: dict) -> str:
        if not isinstance(action, dict):
            return "?"
        a = action.get("action")
        if a == CALL_SKILL:
            return f"call_skill:{action.get('skill_id')}"
        if a == CALL_MCP:
            return f"call_mcp:{action.get('tool')}"
        if a == CREATE_SKILL:
            return f"create_skill:{action.get('name') or ''}"
        if a == CALL_AGENT:
            return f"call_agent:{action.get('agent_id')}"
        if a == FINISH:
            return "finish"
        return str(a)
