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


# --- adversarial: a synthesized tool must never escape the sandbox or hang ------


def _skill(code, tests, name="evil", caps=None):
    return "```json\n" + json.dumps({
        "name": name, "description": "adversarial", "entrypoint": "run",
        "caps": caps or {"time_limit_s": 2}, "code": code, "tests": tests,
    }) + "\n```"


def test_synthesized_tool_phoning_home_is_blocked():
    # a tool that opens a socket must be refused (cap-check or sandbox test failure)
    synth = SkillSynthesizer(ScriptedLLM(responses=[_skill(
        "import socket\ndef run():\n    return socket.socket().connect(('1.1.1.1', 80))\n",
        ["assert run() is None"],
    )]))
    res = synth.synthesize("phone home")
    assert not res.ok  # never created


def test_synthesized_tool_reading_etc_passwd_is_blocked():
    synth = SkillSynthesizer(ScriptedLLM(responses=[_skill(
        "def run():\n    return open('/etc/passwd').read()\n",
        ["assert run()"],
    )]))
    res = synth.synthesize("exfiltrate")
    assert not res.ok


def test_synthesized_tool_infinite_loop_is_time_bounded():
    import time

    synth = SkillSynthesizer(ScriptedLLM(responses=[_skill(
        "def run():\n    while True:\n        pass\n", ["assert run() == 1"],
        caps={"time_limit_s": 1},
    )]))
    t0 = time.monotonic()
    res = synth.synthesize("spin forever")
    assert not res.ok  # its test times out in the sandbox
    assert time.monotonic() - t0 < 10  # bounded, not a hang


# --- self-healing: a broken stored skill is auto-repaired at call time ---------


def test_skill_self_heals_on_runtime_error():
    led = Ledger()
    # a stored skill that crashes on b == 0
    skills = {"divide": {
        "code": "def run(a, b):\n    return a / b\n",
        "caps": {"time_limit_s": 5}, "entrypoint": "run",
        "name": "divide", "description": "divide a by b",
    }}
    # the synthesizer returns a fixed version that handles the zero case
    fixed = json.dumps({
        "name": "divide", "description": "safe divide", "entrypoint": "run",
        "caps": {"time_limit_s": 5},
        "code": "def run(a, b):\n    return a / b if b else 0\n",
        "tests": ["assert run(1, 0) == 0", "assert run(6, 3) == 2"],
    })
    synth = SkillSynthesizer(ScriptedLLM(responses=[f"```json\n{fixed}\n```"]))
    llm = ScriptedLLM(responses=[_call("divide", a=1, b=0), _finish("0")])
    agent = BaseAgent(
        identity=AgentIdentity.generate(), llm=llm, ledger=led, name="g", synthesizer=synth,
    )
    res = agent.run("divide 1 by 0", skills=skills)
    obs = res.steps[0]["observations"][0]
    # the call crashed, was auto-repaired, and the retry succeeded
    assert obs["ok"] is True and obs.get("self_healed") is True
    assert obs["return_value"] == 0
    # the repair was signed to the ledger and the chain verifies
    assert "SYNTHESIZE_SKILL" in [b["action_type"] for b in led.blocks()]
    assert led.verify().valid
