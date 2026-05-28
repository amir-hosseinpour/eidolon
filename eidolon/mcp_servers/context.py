from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class ToolContext:
    """Runtime dependencies a tool handler needs.

    `rest` is an httpx.AsyncClient already bound to the orchestrator base URL
    and pre-loaded with the operator bearer token in its headers. Tests inject
    one wired to ASGITransport(app); production wires one to the live HTTP
    server.
    """

    rest: httpx.AsyncClient


ToolHandler = Callable[[ToolContext, dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
