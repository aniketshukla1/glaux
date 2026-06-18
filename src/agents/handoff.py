"""Capability-gated agent handoff (completes the CALL_AGENT protocol).

The caller mints a short-lived capability token addressed to the target agent,
logs the handoff + grant onto the ledger, and invokes the target's
`accept_handoff` — which verifies the token before doing any work. The token is
the authorization: no valid token, no work.
"""

from __future__ import annotations

from typing import Optional

from core.ledger import Action, Ledger
from identity import issue_token
from identity.keypair import AgentIdentity


def delegate(
    caller_identity: AgentIdentity,
    target_agent,
    goal: str,
    *,
    capability: str,
    ledger: Optional[Ledger] = None,
    ttl: float = 300.0,
    context: Optional[dict] = None,
    skills: Optional[dict] = None,
    task_id: Optional[str] = None,
    cancel=None,
):
    """Delegate `goal` to `target_agent` under a signed capability token.

    Raises :class:`agents.base.HandoffRejected` if the target refuses the token.
    Returns the target's :class:`AgentResult`.
    """
    token = issue_token(caller_identity, target_agent.identity.agent_id, capability, ttl)
    if ledger is not None:
        ledger.append(
            caller_identity,
            Action.CALL_AGENT,
            {
                "target": target_agent.identity.agent_id,
                "capability": capability,
                "expires_at": token.expires_at,
            },
        )
        ledger.append(caller_identity, Action.GRANT, token.to_dict())

    return target_agent.accept_handoff(
        token,
        caller_identity.public_key_b58,
        goal,
        capability=capability,
        context=context,
        skills=skills,
        task_id=task_id,
        cancel=cancel,
    )
