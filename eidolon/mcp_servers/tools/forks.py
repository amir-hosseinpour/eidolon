from __future__ import annotations

from typing import Any

from .._rest import rest_request
from ..context import ToolContext, ToolSpec

_FORK_TYPES = [
    "path_selection",
    "mode_change",
    "cred_disposition",
    "noise_threshold",
    "scope_edge",
]


async def _fork_open(ctx: ToolContext, args: dict[str, Any]) -> Any:
    eid = args.pop("engagement_id")
    return await rest_request(
        ctx.rest, "POST", f"/v1/engagements/{eid}/forks", json=args
    )


async def _fork_list(ctx: ToolContext, args: dict[str, Any]) -> Any:
    eid = args["engagement_id"]
    params = {}
    if "status" in args and args["status"]:
        params["status"] = args["status"]
    return await rest_request(
        ctx.rest, "GET", f"/v1/engagements/{eid}/forks", params=params or None
    )


async def _fork_resolve(ctx: ToolContext, args: dict[str, Any]) -> Any:
    fork_id = args.pop("fork_id")
    return await rest_request(
        ctx.rest, "POST", f"/v1/engagements/forks/{fork_id}/resolve", json=args
    )


FORK_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="fork_open",
        description=(
            "Open a decision fork: a structured pause that asks the operator "
            "to choose. Five fork types map to five common decisions."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string"},
                "fork_type": {"type": "string", "enum": _FORK_TYPES},
                "prompt": {"type": "string", "minLength": 1},
                "context": {"type": "object"},
            },
            "required": ["engagement_id", "fork_type", "prompt"],
            "additionalProperties": False,
        },
        handler=_fork_open,
    ),
    ToolSpec(
        name="fork_list",
        description="List forks for an engagement, optionally filtered by status.",
        input_schema={
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["open", "approved", "denied", "expired"],
                },
            },
            "required": ["engagement_id"],
            "additionalProperties": False,
        },
        handler=_fork_list,
    ),
    ToolSpec(
        name="fork_resolve",
        description="Resolve a decision fork as approved or denied.",
        input_schema={
            "type": "object",
            "properties": {
                "fork_id": {"type": "string"},
                "resolution": {"type": "string", "enum": ["approved", "denied"]},
                "operator": {"type": "string", "minLength": 1},
                "rationale": {"type": "string"},
            },
            "required": ["fork_id", "resolution", "operator"],
            "additionalProperties": False,
        },
        handler=_fork_resolve,
    ),
]
