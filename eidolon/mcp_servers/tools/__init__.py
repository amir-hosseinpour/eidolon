from __future__ import annotations

from ..context import ToolSpec
from .engagements import ENGAGEMENT_TOOLS
from .forks import FORK_TOOLS
from .secrets import SECRET_TOOLS
from .templates import TEMPLATE_TOOLS
from .workspace import WORKSPACE_TOOLS

ALL_TOOLS: list[ToolSpec] = [
    *ENGAGEMENT_TOOLS,
    *FORK_TOOLS,
    *SECRET_TOOLS,
    *TEMPLATE_TOOLS,
    *WORKSPACE_TOOLS,
]


def build_tool_index() -> dict[str, ToolSpec]:
    """Return name -> ToolSpec; raises if duplicate names slip in."""
    index: dict[str, ToolSpec] = {}
    for spec in ALL_TOOLS:
        if spec.name in index:
            raise ValueError(f"duplicate mcp tool name: {spec.name}")
        index[spec.name] = spec
    return index


__all__ = ["ALL_TOOLS", "build_tool_index"]
