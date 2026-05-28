"""MCP server wrappers for the Eidolon orchestrator.

Exposes the orchestrator's REST surface (engagements, forks) plus locally
available libs (secrets broker, templates loader, workspace) as MCP tools so
any MCP-aware AI client can drive an engagement.
"""

from .context import ToolContext, ToolSpec
from .server import build_server, make_context_from_env, run_stdio
from .tools import ALL_TOOLS, build_tool_index

__all__ = [
    "ALL_TOOLS",
    "ToolContext",
    "ToolSpec",
    "build_server",
    "build_tool_index",
    "make_context_from_env",
    "run_stdio",
]
