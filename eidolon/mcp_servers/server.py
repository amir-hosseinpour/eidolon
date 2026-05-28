from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

import httpx

try:  # pragma: no cover - optional at import-time
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError as exc:  # pragma: no cover
    raise SystemExit("mcp python sdk required: pip install mcp") from exc

from .context import ToolContext, ToolSpec
from .tools import build_tool_index

logger = logging.getLogger("eidolon-mcp")

DEFAULT_BASE_URL = "http://127.0.0.1:8765"


def _operator_token() -> str:
    explicit = os.environ.get("EIDOLON_OPERATOR_TOKEN")
    if explicit:
        return explicit
    from ..orchestrator.lib.auth import load_or_create_token

    return load_or_create_token()


def make_context_from_env() -> ToolContext:
    """Build a ToolContext from EIDOLON_* environment variables.

    EIDOLON_ORCHESTRATOR_URL, EIDOLON_OPERATOR_TOKEN, EIDOLON_AGENT_VERIFY_TLS.
    Falls back to the on-disk operator token at $EIDOLON_HOME/orchestrator-token.
    """
    base_url = os.environ.get("EIDOLON_ORCHESTRATOR_URL", DEFAULT_BASE_URL).rstrip("/")
    verify_tls = os.environ.get("EIDOLON_AGENT_VERIFY_TLS", "1") != "0"
    token = _operator_token()
    rest = httpx.AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
        verify=verify_tls,
    )
    return ToolContext(rest=rest)


def _to_mcp_tool(spec: ToolSpec) -> Tool:
    return Tool(
        name=spec.name,
        description=spec.description,
        inputSchema=spec.input_schema,
    )


def _format_result(value: Any) -> list[TextContent]:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, indent=2, default=str)
    return [TextContent(type="text", text=text)]


def build_server(ctx: ToolContext) -> Server:
    """Build an MCP Server bound to the given ToolContext.

    Tests construct a context backed by httpx.ASGITransport so they can drive
    the FastAPI app in-process. Production wires it to the real HTTP server.
    """
    server: Server = Server("eidolon-mcp")
    index = build_tool_index()

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return [_to_mcp_tool(spec) for spec in index.values()]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        spec = index.get(name)
        if spec is None:
            return _format_result({"ok": False, "reason": f"unknown_tool: {name}"})
        try:
            result = await spec.handler(ctx, dict(arguments))
        except Exception as exc:  # noqa: BLE001
            logger.exception("mcp tool failed: %s", name)
            return _format_result(
                {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
            )
        return _format_result(result)

    return server


async def _serve(ctx: ToolContext) -> None:
    server = build_server(ctx)
    init_options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        try:
            await server.run(read_stream, write_stream, init_options)
        finally:
            await ctx.rest.aclose()


def run_stdio() -> int:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    ctx = make_context_from_env()
    try:
        asyncio.run(_serve(ctx))
    except KeyboardInterrupt:
        logger.info("stdio server interrupted")
    return 0


def cli_main() -> None:
    sys.exit(run_stdio())


if __name__ == "__main__":  # pragma: no cover
    cli_main()
