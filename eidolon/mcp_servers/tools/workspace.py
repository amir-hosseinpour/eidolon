from __future__ import annotations

from typing import Any

from ...orchestrator.lib.workspace import EngagementWorkspace, WorkspaceError
from ..context import ToolContext, ToolSpec


def _ws(engagement_id: str) -> EngagementWorkspace:
    return EngagementWorkspace(engagement_id)


async def _workspace_write_note(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        path = _ws(args["engagement_id"]).write_note(
            args["body"], date=args.get("date")
        )
    except WorkspaceError as exc:
        return {"ok": False, "reason": exc.reason}
    return {"ok": True, "path": str(path)}


async def _workspace_write_decision(
    _ctx: ToolContext, args: dict[str, Any]
) -> dict[str, Any]:
    try:
        path = _ws(args["engagement_id"]).write_decision(
            args["fork_id"],
            prompt=args["prompt"],
            resolution=args["resolution"],
            operator=args["operator"],
            rationale=args.get("rationale", ""),
        )
    except WorkspaceError as exc:
        return {"ok": False, "reason": exc.reason}
    return {"ok": True, "path": str(path)}


async def _workspace_write_finding(
    _ctx: ToolContext, args: dict[str, Any]
) -> dict[str, Any]:
    try:
        path = _ws(args["engagement_id"]).write_finding(
            args["title"],
            severity=args["severity"],
            body=args["body"],
            cwe=args.get("cwe"),
        )
    except WorkspaceError as exc:
        return {"ok": False, "reason": exc.reason}
    return {"ok": True, "path": str(path)}


async def _workspace_read_log(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"events": _ws(args["engagement_id"]).read_log()}


WORKSPACE_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="workspace_write_note",
        description=(
            "Append a dated note to notes/YYYY-MM-DD.md in the engagement "
            "workspace. Notes are operator-visible Markdown."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string"},
                "body": {"type": "string", "minLength": 1},
                "date": {"type": "string"},
            },
            "required": ["engagement_id", "body"],
            "additionalProperties": False,
        },
        handler=_workspace_write_note,
    ),
    ToolSpec(
        name="workspace_write_decision",
        description=(
            "Write a decision record under decisions/<fork>.md tying a fork "
            "resolution back to its operator and rationale."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string"},
                "fork_id": {"type": "string"},
                "prompt": {"type": "string"},
                "resolution": {"type": "string"},
                "operator": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": [
                "engagement_id",
                "fork_id",
                "prompt",
                "resolution",
                "operator",
            ],
            "additionalProperties": False,
        },
        handler=_workspace_write_decision,
    ),
    ToolSpec(
        name="workspace_write_finding",
        description="Write a finding under findings/<slug>.md.",
        input_schema={
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string"},
                "title": {"type": "string", "minLength": 1},
                "severity": {"type": "string"},
                "body": {"type": "string"},
                "cwe": {"type": "string"},
            },
            "required": ["engagement_id", "title", "severity", "body"],
            "additionalProperties": False,
        },
        handler=_workspace_write_finding,
    ),
    ToolSpec(
        name="workspace_read_log",
        description="Read the workspace event log (workspace_init, note_appended, etc).",
        input_schema={
            "type": "object",
            "properties": {"engagement_id": {"type": "string"}},
            "required": ["engagement_id"],
            "additionalProperties": False,
        },
        handler=_workspace_read_log,
    ),
]
