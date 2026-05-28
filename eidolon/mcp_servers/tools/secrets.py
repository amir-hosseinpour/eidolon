from __future__ import annotations

from typing import Any

from ...orchestrator.lib.secrets import SecretsBroker, SecretsError
from ..context import ToolContext, ToolSpec


def _broker() -> SecretsBroker:
    return SecretsBroker()


async def _secret_put(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        _broker().put(args["label"], args["value"])
    except SecretsError as exc:
        return {"ok": False, "reason": exc.reason}
    return {"ok": True, "label": args["label"]}


async def _secret_delete(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        existed = _broker().delete(args["label"])
    except SecretsError as exc:
        return {"ok": False, "reason": exc.reason}
    return {"ok": True, "label": args["label"], "existed": existed}


async def _secret_present(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        value = _broker().get(args["label"])
    except SecretsError as exc:
        return {"ok": False, "reason": exc.reason}
    return {"present": value is not None, "label": args["label"]}


SECRET_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="secret_put",
        description=(
            "Store a secret in the operator's broker (env / Keychain / 1Password). "
            "Does NOT return the value back. Labels are lowercase a-z0-9_."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "label": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9_]{0,62}$"},
                "value": {"type": "string", "minLength": 1},
            },
            "required": ["label", "value"],
            "additionalProperties": False,
        },
        handler=_secret_put,
    ),
    ToolSpec(
        name="secret_delete",
        description="Delete a secret by label. Returns whether one existed.",
        input_schema={
            "type": "object",
            "properties": {
                "label": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9_]{0,62}$"},
            },
            "required": ["label"],
            "additionalProperties": False,
        },
        handler=_secret_delete,
    ),
    ToolSpec(
        name="secret_present",
        description=(
            "Check whether a secret label resolves. Does NOT return the value "
            "(in-VM tools fetch values via the eidolon-agent socket)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "label": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9_]{0,62}$"},
            },
            "required": ["label"],
            "additionalProperties": False,
        },
        handler=_secret_present,
    ),
]
