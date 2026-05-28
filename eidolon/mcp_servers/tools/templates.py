from __future__ import annotations

from typing import Any

from ...orchestrator.lib.templates import (
    TemplateValidationError,
    list_templates,
    load_template_by_name,
)
from ..context import ToolContext, ToolSpec


def _summarize(loaded: Any) -> dict[str, Any]:
    tmpl = loaded.template
    return {
        "name": tmpl.name,
        "version": tmpl.version,
        "description": tmpl.description,
        "substrate_support": list(tmpl.substrate_support),
        "vms": [v.name for v in tmpl.vms],
        "secrets_required": list(tmpl.secrets_required),
        "directory": str(loaded.directory),
    }


async def _template_list(_ctx: ToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    return {"templates": [_summarize(t) for t in list_templates()]}


async def _template_info(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        loaded = load_template_by_name(args["name"])
    except TemplateValidationError as exc:
        return {"ok": False, "reason": exc.reason, "template_dir": str(exc.template_dir)}
    return {
        "ok": True,
        "summary": _summarize(loaded),
        "template": loaded.template.model_dump(),
    }


TEMPLATE_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="template_list",
        description=(
            "List available engagement templates (operator-supplied + bundled). "
            "Operator templates win on name collision."
        ),
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_template_list,
    ),
    ToolSpec(
        name="template_info",
        description="Get the full validated template document by name.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=_template_info,
    ),
]
