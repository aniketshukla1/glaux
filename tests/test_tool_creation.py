"""On-the-fly tool creation: an agent synthesizes a tool mid-task and calls it."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("athena_ledger")

import safety  # noqa: E402
from agents import BaseAgent  # noqa: E402
from core.ledger import Ledger  # noqa: E402
from identity import AgentIdentity  # noqa: E402
from llm import ScriptedLLM  # noqa: E402
from skills import SkillSynthesizer  # noqa: E402


@pytest.fixture(autouse=True)
def _live():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


def _create(name, task):
    return f'```json\n{{"action": "create_skill", "name": "{name}", "task": {json.dumps(task)}}}\n```'


def _call(sid, **args):
    return f'```json\n{{"action": "call_skill", "skill_id": "{sid}", "args": {json.dumps(args)}}}\n```'


def _finish(r):
    return f'```json\n{{"action": "finish", "result": "{r}", "success": true}}\n```'


# A scripted synthesizer response: a real slugify skill with a passing test.
_SKILL_JSON = json.dumps({
    "name": "slugify",
    "description": "turn a title into a url slug",
    "entrypoint": "run",
    "caps": {"time_limit_s": 5},
    "code": "import re\ndef run(text):\n    return re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')\n",
    "tests": ["assert run('Hello World') == 'hello-world'"],
})


def test_agent_creates_a_tool_then_uses_it_in_the_same_run():
    led = Ledger()
    synth = SkillSynthesizer(ScriptedLLM(responses=[f"```json\n{_SKILL_JSON}\n```"]))
    agent_llm = ScriptedLLM(responses=[
        _create("slugify", "convert a title to a url slug"),
        _call("slugify", text="Hello World"),
        _finish("hello-world"),
    ])
    agent = BaseAgent(
        identity=AgentIdentity.generate(), llm=agent_llm, ledger=led,
        name="generalist", synthesizer=synth,
    )
    res = agent.run("slugify the title 'Hello World'")
    assert res.success
    # step 0 created the tool (synthesized + sandbox-tested)
    created = res.steps[0]["observations"][0]
    assert created["ok"] is True and created["created"] == "slugify"
    # step 1 called the freshly-created tool; it ran in the sandbox
    assert res.steps[1]["observations"][0]["return_value"] == "hello-world"
    # the creation was signed to the ledger and the chain still verifies
    assert "SYNTHESIZE_SKILL" in [b["action_type"] for b in led.blocks()]
    assert led.verify().valid


def test_create_skill_disabled_without_a_synthesizer():
    llm = ScriptedLLM(responses=[_create("x", "do x"), _finish("answered directly")])
    agent = BaseAgent(identity=AgentIdentity.generate(), llm=llm, name="t")  # no synthesizer
    res = agent.run("do x")
    assert res.steps[0]["observations"][0]["ok"] is False
    assert "not enabled" in res.steps[0]["observations"][0]["error"]
    assert res.success  # the agent recovered and finished


def test_failed_synthesis_is_reported_not_crashed():
    synth = SkillSynthesizer(ScriptedLLM(responses=["not valid skill json"]))
    llm = ScriptedLLM(responses=[_create("x", "do x"), _finish("fell back")])
    agent = BaseAgent(identity=AgentIdentity.generate(), llm=llm, name="t", synthesizer=synth)
    res = agent.run("do x")
    obs = res.steps[0]["observations"][0]
    assert obs["ok"] is False and "synthesis failed" in obs["error"]
    assert res.success  # a failed synthesis is a recoverable observation, not a crash
