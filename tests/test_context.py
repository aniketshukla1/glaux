"""Long-horizon context management: the HISTORY stays under a char budget."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.context import CompactionStats, ContextManager  # noqa: E402


def _step(i, thought, actions=None, observations=None):
    return {
        "iteration": i,
        "thought": thought,
        "actions": actions or [],
        "observations": observations if observations is not None else [],
    }


def test_empty_history_is_noop():
    cm = ContextManager()
    lines, stats = cm.render_history([])
    assert lines == []
    assert stats == CompactionStats() and stats.compacted is False


def test_small_history_is_all_verbatim():
    cm = ContextManager(max_history_chars=6000, keep_recent_steps=3)
    sp = [_step(0, "first thought", [{"action": "finish"}], [{"ok": True, "return_value": 42}])]
    lines, stats = cm.render_history(sp)
    assert lines[0] == "HISTORY:"
    assert stats.verbatim == 1 and stats.digested == 0 and stats.elided == 0
    assert stats.compacted is False
    text = "\n".join(lines)
    assert "first thought" in text and "42" in text


def test_budget_is_never_exceeded_under_huge_history():
    cm = ContextManager(max_history_chars=1500, keep_recent_steps=3)
    sp = [
        _step(i, "x" * 2000, [{"action": "call_mcp", "tool": f"t{i}"}], [{"ok": False, "error": "boom"}])
        for i in range(40)
    ]
    lines, stats = cm.render_history(sp)
    assert stats.total_steps == 40
    assert stats.compacted is True
    assert stats.verbatim >= 1  # the newest step always survives verbatim
    assert stats.chars <= 1500
    # header ("HISTORY:") + the elided marker line are the only slack over budget
    assert len("\n".join(lines)) <= 1500 + 200


def test_keep_recent_caps_verbatim_rest_digested():
    cm = ContextManager(max_history_chars=100_000, keep_recent_steps=2)
    sp = [_step(i, f"t{i}", [{"action": "call_skill", "skill_id": f"s{i}"}]) for i in range(10)]
    _lines, stats = cm.render_history(sp)
    assert stats.verbatim == 2  # only the 2 most recent kept verbatim
    assert stats.digested == 8  # budget is huge, so the rest are digests, not elided
    assert stats.elided == 0


def test_digest_carries_action_signature_and_error():
    cm = ContextManager(max_history_chars=100_000, keep_recent_steps=1)
    sp = [
        _step(0, "trying a search", [{"action": "call_mcp", "tool": "search"}], [{"ok": False, "error": "timed out"}]),
        _step(1, "wrapping up", [{"action": "finish"}], [{"ok": True}]),
    ]
    lines, _ = cm.render_history(sp)
    text = "\n".join(lines)
    assert "call_mcp:search" in text  # step 0 is a digest (keep_recent=1) → action sig shown
    assert "timed out" in text  # the digest carries the failure reason
    assert "wrapping up" in text  # step 1 is verbatim → its thought is shown in full


def test_newest_survives_verbatim_and_oldest_elided():
    cm = ContextManager(max_history_chars=900, keep_recent_steps=1, thought_chars=200, obs_chars=80)
    sp = [
        _step(i, f"MARK{i} " + "detail " * 40, [{"action": "call_skill", "skill_id": f"s{i}"}], [{"ok": i % 2 == 0}])
        for i in range(30)
    ]
    lines, stats = cm.render_history(sp)
    text = "\n".join(lines)
    assert "MARK29" in text  # the freshest step is present verbatim
    assert stats.elided > 0  # deep history dropped to fit the budget
    assert stats.chars <= 900


def test_chronological_order_preserved():
    cm = ContextManager(max_history_chars=100_000, keep_recent_steps=3)
    sp = [_step(i, f"MARK{i}") for i in range(6)]
    lines, _ = cm.render_history(sp)
    text = "\n".join(lines)
    positions = [text.index(f"MARK{i}") for i in range(6)]
    assert positions == sorted(positions)


def test_legacy_singular_observation_is_read():
    cm = ContextManager()
    sp = [{"iteration": 0, "thought": "t", "actions": [], "observation": {"ok": True, "return_value": "legacy"}}]
    lines, _ = cm.render_history(sp)
    assert "legacy" in "\n".join(lines)


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("ATHENA_CONTEXT_MAX_CHARS", "1234")
    monkeypatch.setenv("ATHENA_CONTEXT_KEEP_RECENT", "5")
    cm = ContextManager.from_env()
    assert cm.max_history_chars == 1234 and cm.keep_recent_steps == 5


def test_summarize_hook_folds_the_elided_steps():
    seen = {}

    def summarize(steps):
        seen["n"] = len(steps)
        return "PRIOR_PROGRESS_DIGEST"

    cm = ContextManager(max_history_chars=500, keep_recent_steps=1, summarize=summarize)
    sp = [_step(i, "x" * 400) for i in range(10)]
    lines, stats = cm.render_history(sp)
    text = "\n".join(lines)
    assert "PRIOR_PROGRESS_DIGEST" in text
    assert stats.elided > 0 and seen["n"] == stats.elided


def test_summarize_hook_failure_falls_back_to_count():
    def boom(_steps):
        raise RuntimeError("summarizer down")

    cm = ContextManager(max_history_chars=500, keep_recent_steps=1, summarize=boom)
    sp = [_step(i, "x" * 400) for i in range(10)]
    lines, stats = cm.render_history(sp)
    text = "\n".join(lines)
    assert "elided" in text and stats.elided > 0  # degraded gracefully, no crash


# --- integration: a real ReAct run compacts + signs the compaction ---------


def _call(sid, **args):
    return f'```json\n{{"action": "call_skill", "skill_id": "{sid}", "args": {json.dumps(args)}}}\n```'


def _finish(r):
    return f'```json\n{{"action": "finish", "result": "{r}", "success": true}}\n```'


def test_base_agent_compacts_long_history_and_signs_it():
    pytest.importorskip("athena_ledger")
    from agents import BaseAgent
    from core.ledger import Ledger
    from identity import AgentIdentity
    from llm import ScriptedLLM

    led = Ledger()
    pad = "reasoning carefully about the sub-problem step by step. " * 6  # ~330 chars/step
    responses = [pad + _call(f"tool_{i}", x=i) for i in range(4)] + [pad + _finish("done")]
    agent = BaseAgent(
        identity=AgentIdentity.generate(),
        llm=ScriptedLLM(responses=responses),
        ledger=led,
        name="generalist",
        context_manager=ContextManager(max_history_chars=400, keep_recent_steps=1),
    )
    res = agent.run("a long multi-step task")

    assert res.success and res.result == "done"
    # by the final turn the history overflowed the 400-char budget and compacted
    assert res.context["compacted"] is True
    assert res.context["total_steps"] >= 3 and res.context["elided"] + res.context["digested"] > 0
    # the compaction is signed onto the ledger, and the chain still verifies
    assert "COMPACT_CONTEXT" in [b["action_type"] for b in led.blocks()]
    assert led.verify().valid
