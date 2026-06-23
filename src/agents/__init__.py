"""Athena agents and swarm."""

from .base import AgentResult, BaseAgent, HandoffRejected
from .budget import Budget, BudgetTracker
from .handoff import delegate
from .mcp import (
    HTTPMCPClient,
    LocalMCPClient,
    MCPClient,
    MCPRegistry,
    MCPServerConfig,
    MCPTool,
    StdioMCPClient,
    default_local_client,
    make_client,
)
from .protocol import CALL_AGENT, CALL_MCP, CALL_SKILL, FINISH, extract_json, parse_action
from .web import (
    SEARCH_PROVIDERS,
    begin_source_capture,
    collected_sources,
    configure_search,
    default_browser_client,
    search_status,
    web_fetch,
    web_search,
)
from .reflector import Reflector, Verdict
from .router import Plan, Router, Step
from .specialists import SPECIALISTS, build_specialists, coder_agent, make_specialist, researcher_agent
from .swarm import StepResult, Swarm, SwarmResult, topo_sort

__all__ = [
    "BaseAgent",
    "AgentResult",
    "HandoffRejected",
    "Budget",
    "BudgetTracker",
    "delegate",
    "parse_action",
    "extract_json",
    "FINISH",
    "CALL_SKILL",
    "CALL_AGENT",
    "CALL_MCP",
    "MCPClient",
    "MCPTool",
    "LocalMCPClient",
    "StdioMCPClient",
    "HTTPMCPClient",
    "MCPRegistry",
    "MCPServerConfig",
    "make_client",
    "default_local_client",
    "default_browser_client",
    "configure_search",
    "search_status",
    "SEARCH_PROVIDERS",
    "web_fetch",
    "web_search",
    "Router",
    "Plan",
    "Step",
    "Reflector",
    "Verdict",
    "coder_agent",
    "researcher_agent",
    "make_specialist",
    "build_specialists",
    "SPECIALISTS",
    "Swarm",
    "SwarmResult",
    "StepResult",
    "topo_sort",
]
