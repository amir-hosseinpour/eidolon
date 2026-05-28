from __future__ import annotations

import time

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from ...lib.audit import emit_audit
from ...lib.dispatches import get_dispatch_store
from ...lib.scope import ScopeAction, ScopeError, ScopeTier, verify_scope_token

router = APIRouter()


AUTONOMOUS_TOOLS: set[str] = {
    "recon.nmap.tcp-top-1000",
    "recon.http.fingerprint",
    "recon.dns.enum",
    "analyst.summarize",
    "report.read",
}

CONFIRM_TOOLS: set[str] = {
    "recon.nmap.full",
    "recon.nuclei.scan",
    "exploit.msf.auxiliary",
    "crack.hashcat.offline",
    "sandbox.exec.shell",
}

PROHIBITED_TOOLS: set[str] = {
    "exploit.ransomware.deploy",
    "exploit.data.exfiltrate",
    "persist.backdoor.install",
}


class ToolDispatchRequest(BaseModel):
    engagement_id: str
    tool_id: str
    target: str | None = None
    action: ScopeAction
    args: dict[str, str] = Field(default_factory=dict)
    confirm_token: str | None = Field(
        default=None,
        description="Operator-supplied confirmation for confirm-tier tools.",
    )


class ToolDispatchResponse(BaseModel):
    accepted: bool
    tier: ScopeTier
    reason: str | None = None
    dispatch_id: str | None = None


def _resolve_tier(tool_id: str) -> ScopeTier:
    if tool_id in PROHIBITED_TOOLS:
        return "prohibited"
    if tool_id in CONFIRM_TOOLS:
        return "confirm"
    if tool_id in AUTONOMOUS_TOOLS:
        return "autonomous"
    raise KeyError(f"unknown tool: {tool_id}")


@router.post("/dispatch", response_model=ToolDispatchResponse)
async def tool_dispatch(
    req: ToolDispatchRequest,
    x_scope_token: str = Header(...),
) -> ToolDispatchResponse:
    try:
        tier = _resolve_tier(req.tool_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"reason": "tool_unknown"}) from exc

    try:
        verified = verify_scope_token(
            x_scope_token,
            expected_engagement=req.engagement_id,
            target=req.target,
            action=req.action,
            requested_tier=tier,
        )
    except ScopeError as exc:
        emit_audit(
            "tool_dispatch_denied",
            engagement_id=req.engagement_id,
            tier=tier,
            reason=exc.reason,
            target=req.target,
            action=req.action,
        )
        raise HTTPException(status_code=exc.status_code, detail={"reason": exc.reason}) from exc

    dispatch_id = f"DSP-{verified.engagement_id}-{req.tool_id}-{int(time.time() * 1000)}"

    if tier == "prohibited":
        emit_audit(
            "tool_dispatch_denied",
            engagement_id=verified.engagement_id,
            tier=tier,
            reason="tier_prohibited",
            target=req.target,
            action=req.action,
        )
        get_dispatch_store().record(
            dispatch_id=dispatch_id,
            engagement_id=verified.engagement_id,
            jti=verified.jti,
            tool_id=req.tool_id,
            target=req.target,
            action=req.action,
            tier=tier,
            accepted=False,
            reason="tier_prohibited",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason": "tier_prohibited"},
        )

    if tier == "confirm" and not req.confirm_token:
        get_dispatch_store().record(
            dispatch_id=dispatch_id,
            engagement_id=verified.engagement_id,
            jti=verified.jti,
            tool_id=req.tool_id,
            target=req.target,
            action=req.action,
            tier=tier,
            accepted=False,
            reason="confirm_token_required",
        )
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={"reason": "confirm_token_required"},
        )

    emit_audit(
        "tool_dispatch_accepted",
        engagement_id=verified.engagement_id,
        jti=verified.jti,
        tier=tier,
        target=req.target,
        action=req.action,
        dispatch_id=dispatch_id,
    )
    get_dispatch_store().record(
        dispatch_id=dispatch_id,
        engagement_id=verified.engagement_id,
        jti=verified.jti,
        tool_id=req.tool_id,
        target=req.target,
        action=req.action,
        tier=tier,
        accepted=True,
        reason=None,
    )
    return ToolDispatchResponse(
        accepted=True,
        tier=tier,
        dispatch_id=dispatch_id,
    )
