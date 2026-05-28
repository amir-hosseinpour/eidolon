from __future__ import annotations

from typing import Any

from .._rest import rest_request
from ..context import ToolContext, ToolSpec

_SCOPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "allowed_cidrs": {"type": "array", "items": {"type": "string"}},
        "allowed_actions": {"type": "array", "items": {"type": "string"}},
        "tier": {
            "type": "string",
            "enum": ["autonomous", "confirm", "prohibited"],
        },
        "rules_of_engagement": {"type": "string"},
        "expires_at": {"type": "integer"},
    },
    "required": ["allowed_cidrs", "allowed_actions", "tier"],
    "additionalProperties": False,
}


async def _engage_start(ctx: ToolContext, args: dict[str, Any]) -> Any:
    return await rest_request(ctx.rest, "POST", "/v1/engagements/start", json=args)


async def _engage_list(ctx: ToolContext, _args: dict[str, Any]) -> Any:
    return await rest_request(ctx.rest, "GET", "/v1/engagements")


async def _engage_get(ctx: ToolContext, args: dict[str, Any]) -> Any:
    return await rest_request(
        ctx.rest, "GET", f"/v1/engagements/{args['engagement_id']}"
    )


async def _engage_close(ctx: ToolContext, args: dict[str, Any]) -> Any:
    return await rest_request(
        ctx.rest, "POST", f"/v1/engagements/{args['engagement_id']}/close", json={}
    )


async def _engage_erase(ctx: ToolContext, args: dict[str, Any]) -> Any:
    return await rest_request(
        ctx.rest, "POST", f"/v1/engagements/{args['engagement_id']}/erase", json={}
    )


async def _scope_token_issue(ctx: ToolContext, args: dict[str, Any]) -> Any:
    eid = args.pop("engagement_id")
    return await rest_request(
        ctx.rest, "POST", f"/v1/engagements/{eid}/scope-token", json=args
    )


async def _scope_token_revoke(ctx: ToolContext, args: dict[str, Any]) -> Any:
    eid = args["engagement_id"]
    await rest_request(
        ctx.rest,
        "POST",
        f"/v1/engagements/{eid}/scope-token/revoke",
        json={"jti": args["jti"]},
    )
    return {"ok": True, "engagement_id": eid, "jti": args["jti"]}


ENGAGEMENT_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="engage_start",
        description=(
            "Start a new engagement. Validates the scope document, persists "
            "the engagement record, and issues an initial scope token."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "purpose": {
                    "type": "string",
                    "enum": ["pentest", "research", "ctf", "training"],
                },
                "scope": _SCOPE_SCHEMA,
            },
            "required": ["slug", "purpose", "scope"],
            "additionalProperties": False,
        },
        handler=_engage_start,
    ),
    ToolSpec(
        name="engage_list",
        description="List all engagements visible to the orchestrator.",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_engage_list,
    ),
    ToolSpec(
        name="engage_get",
        description="Fetch a single engagement by id.",
        input_schema={
            "type": "object",
            "properties": {"engagement_id": {"type": "string"}},
            "required": ["engagement_id"],
            "additionalProperties": False,
        },
        handler=_engage_get,
    ),
    ToolSpec(
        name="engage_close",
        description=(
            "Close an engagement. Revokes scope tokens; preserves workspace "
            "on disk. Use engage_erase to nuke."
        ),
        input_schema={
            "type": "object",
            "properties": {"engagement_id": {"type": "string"}},
            "required": ["engagement_id"],
            "additionalProperties": False,
        },
        handler=_engage_close,
    ),
    ToolSpec(
        name="engage_erase",
        description="Erase an engagement (close if active, then mark erased).",
        input_schema={
            "type": "object",
            "properties": {"engagement_id": {"type": "string"}},
            "required": ["engagement_id"],
            "additionalProperties": False,
        },
        handler=_engage_erase,
    ),
    ToolSpec(
        name="scope_token_issue",
        description=(
            "Issue an additional scope token under an existing engagement. "
            "Bound to a target/permit/tier triple."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string"},
                "targets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "permits": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "tier": {
                    "type": "string",
                    "enum": ["autonomous", "confirm", "prohibited"],
                },
                "ttl_seconds": {"type": "integer", "minimum": 1, "maximum": 86400},
                "rules_of_engagement": {"type": "string"},
            },
            "required": ["engagement_id", "targets", "permits", "tier"],
            "additionalProperties": False,
        },
        handler=_scope_token_issue,
    ),
    ToolSpec(
        name="scope_token_revoke",
        description="Revoke a scope token by jti.",
        input_schema={
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string"},
                "jti": {"type": "string"},
            },
            "required": ["engagement_id", "jti"],
            "additionalProperties": False,
        },
        handler=_scope_token_revoke,
    ),
]
