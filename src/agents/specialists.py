"""Specialist agents — a roster of BaseAgents differentiated by role prompt.

Each specialist shares the same signed, sandboxed ReAct machinery (see
:mod:`agents.base`); they differ in their system prompt, the capability the
router hands them, and how long they are allowed to grind toward a correct
answer (`iterations`). The router reads each role's one-line `description` to
compose a *team* per directive — a research lab for a science question, an
engineering pod for a build, an analysis desk for a comparison — so different
directives spin up genuinely different swarms.

Adding a specialist is data-only: add an entry to ``SPECIALISTS``. ``api.py``
mints an identity per role and registers them all with the swarm.
"""

from __future__ import annotations

from .base import ACTION_INSTRUCTIONS, BaseAgent

# role -> { description, iterations, prompt }
#   description : one line the router uses to pick the right specialist
#   iterations  : ReAct budget; hard roles grind longer (budget still bounds the task)
#   prompt      : the role's system prompt (ACTION_INSTRUCTIONS are appended)
SPECIALISTS: dict[str, dict] = {
    "researcher": {
        "description": "gathers, verifies and synthesizes information into clear, sourced answers",
        "iterations": 8,
        "prompt": (
            "You are {name}, a research specialist in the Athena swarm. You gather, "
            "cross-check and synthesize information into clear, well-supported answers. "
            "Separate what is established from what is uncertain, and never state a fact "
            "you cannot justify."
        ),
    },
    "web": {
        "description": "reads live web pages and search results via tools, then cites what it found",
        "iterations": 10,
        "prompt": (
            "You are {name}, a web-research specialist in the Athena swarm. Use the "
            "available MCP tools to search the web and fetch pages, then ground every "
            "claim in what you actually retrieved. Quote sparingly and cite the source "
            "URL for each key fact. Never invent a URL, a quote, or a result you did not "
            "fetch — if the tools return nothing useful, say so."
        ),
    },
    "scientist": {
        "description": "explains scientific and technical mechanisms rigorously (biology, chemistry, physics)",
        "iterations": 9,
        "prompt": (
            "You are {name}, a scientific specialist in the Athena swarm. You explain "
            "mechanisms at the right level of detail: define the key terms, lay out the "
            "steps in order, name the molecules / forces / actors involved, and call out "
            "the common misconceptions. Be precise; prefer mechanism over hand-waving."
        ),
    },
    "analyst": {
        "description": "does quantitative analysis, comparisons and structured trade-off breakdowns",
        "iterations": 8,
        "prompt": (
            "You are {name}, an analysis specialist in the Athena swarm. You reason "
            "quantitatively and structurally: break a question into criteria, weigh the "
            "options against each one, surface the trade-offs explicitly, and end with a "
            "clear, justified recommendation. Show the numbers behind any conclusion."
        ),
    },
    "coder": {
        "description": "writes, runs and debugs code via sandboxed skills",
        "iterations": 8,
        "prompt": (
            "You are {name}, a coding specialist in the Athena swarm. You solve tasks by "
            "calling skills that write, transform, or compute. Prefer existing skills, "
            "keep outputs precise, and verify your result before finishing."
        ),
    },
    "engineer": {
        "description": "designs systems and architectures; plans multi-component, real-world solutions",
        "iterations": 9,
        "prompt": (
            "You are {name}, a systems-engineering specialist in the Athena swarm. You "
            "design real-world solutions: state the requirements and constraints, lay out "
            "the components and how they interact, justify the key technology choices "
            "against alternatives, and call out failure modes, scaling limits and a "
            "rollback path. Think in phases."
        ),
    },
    "tester": {
        "description": "designs and runs tests, hunts edge cases and verifies correctness",
        "iterations": 7,
        "prompt": (
            "You are {name}, a verification specialist in the Athena swarm. You stress "
            "what others build: enumerate edge cases and failure conditions, design tests "
            "that would catch them, run what you can via skills, and report exactly what "
            "passed, what failed, and what is still unverified."
        ),
    },
    "writer": {
        "description": "turns findings into clear long-form explanations, documents and summaries",
        "iterations": 6,
        "prompt": (
            "You are {name}, a writing specialist in the Athena swarm. You turn the "
            "swarm's findings into clear, well-structured prose for a smart non-expert: "
            "lead with the answer, use headings and lists where they help, define jargon "
            "on first use, and stay faithful to the upstream results — add nothing the "
            "evidence does not support."
        ),
    },
}


def _role_prompt(prompt: str, name: str, lessons=None) -> str:
    base = prompt.format(name=name) + "\n" + ACTION_INSTRUCTIONS
    if lessons:
        base += "\n\nLEARNED LESSONS (from past runs — heed them):\n" + "\n".join(f"- {le}" for le in lessons)
    return base


def make_specialist(
    role: str, *, identity, llm, name: str | None = None,
    iterations: int | None = None, lessons=None, **kwargs,
) -> BaseAgent:
    """Build a single specialist by role name from the registry. The self-evolving
    harness may override the iteration budget and inject learned lessons."""
    spec = SPECIALISTS[role]
    name = name or role
    agent = BaseAgent(
        identity=identity,
        llm=llm,
        name=name,
        system_prompt=_role_prompt(spec["prompt"], name, lessons),
        max_iterations=iterations if iterations is not None else spec.get("iterations", 8),
        **kwargs,
    )
    # Read by the router to compose a team for each directive.
    agent.description = spec["description"]
    return agent


def build_specialists(
    *, identities: dict, llm, budget_overrides=None, lessons=None, **kwargs,
) -> dict[str, BaseAgent]:
    """Build the full specialist roster, one agent per role in ``SPECIALISTS``.

    `identities` must contain an :class:`AgentIdentity` for every specialist role.
    `budget_overrides` / `lessons` are the self-evolving harness's learned per-role
    tweaks. Extra kwargs (ledger, mcp_client, …) are forwarded to each agent.
    """
    budget_overrides = budget_overrides or {}
    lessons = lessons or {}
    return {
        role: make_specialist(
            role, identity=identities[role], llm=llm,
            iterations=budget_overrides.get(role), lessons=lessons.get(role), **kwargs,
        )
        for role in SPECIALISTS
    }


# --- back-compat thin wrappers (used by older call sites / tests) -------------

def coder_agent(*, identity, llm, name: str = "coder", **kwargs) -> BaseAgent:
    return make_specialist("coder", identity=identity, llm=llm, name=name, **kwargs)


def researcher_agent(*, identity, llm, name: str = "researcher", **kwargs) -> BaseAgent:
    return make_specialist("researcher", identity=identity, llm=llm, name=name, **kwargs)
