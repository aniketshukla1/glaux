"""Specialist agents — BaseAgents differentiated by role prompt.

`coder` writes/runs code via skills; `researcher` gathers and synthesizes
information. Both share the ReAct machinery; they differ in their system prompt
(and, as memory wiring matures, in which memory partitions they lean on).
"""

from __future__ import annotations

from .base import ACTION_INSTRUCTIONS, BaseAgent

CODER_ROLE = (
    "You are {name}, a coding specialist in the Athena swarm. You solve tasks by "
    "calling skills that write, transform, or compute. Prefer existing skills; keep "
    "outputs precise."
)

RESEARCHER_ROLE = (
    "You are {name}, a research specialist in the Athena swarm. You gather, verify, "
    "and synthesize information into clear, well-supported answers."
)


def _role_prompt(role_template: str, name: str) -> str:
    return role_template.format(name=name) + "\n" + ACTION_INSTRUCTIONS


def coder_agent(*, identity, llm, name: str = "coder", **kwargs) -> BaseAgent:
    return BaseAgent(
        identity=identity,
        llm=llm,
        name=name,
        system_prompt=_role_prompt(CODER_ROLE, name),
        **kwargs,
    )


def researcher_agent(*, identity, llm, name: str = "researcher", **kwargs) -> BaseAgent:
    return BaseAgent(
        identity=identity,
        llm=llm,
        name=name,
        system_prompt=_role_prompt(RESEARCHER_ROLE, name),
        **kwargs,
    )
