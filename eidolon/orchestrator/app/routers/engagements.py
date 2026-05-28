from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ...lib.audit import emit_audit, get_audit_chain
from ...lib.engagements import Engagement, EngagementStatus, EngagementStore
from ...lib.provisioner import (
    ProvisionedVM,
    Provisioner,
    ProvisionError,
    ProvisionResult,
)
from ...lib.revocation import get_revocation_store
from ...lib.scope import ScopeAction, ScopeDocument, ScopeTier, issue_scope_token
from ...lib.templates import (
    TemplateValidationError,
    load_template_by_name,
)

router = APIRouter()
store = EngagementStore()
provisioner = Provisioner(engagement_store=store)


def _override_provisioner(p: Provisioner) -> None:
    """Test hook: replace the module-level provisioner for in-memory substrates."""
    global provisioner
    provisioner = p


class EngagementStartRequest(BaseModel):
    slug: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    purpose: str = Field(..., pattern=r"^(pentest|research|ctf|training)$")
    scope: ScopeDocument


class EngagementStartResponse(BaseModel):
    engagement_id: str
    scope_token: str
    jti: str
    expires_at: int
    status: EngagementStatus


class EngagementStatusResponse(BaseModel):
    engagement: Engagement


class EngagementListResponse(BaseModel):
    engagements: list[Engagement]


class IssuedTokensResponse(BaseModel):
    jtis: list[str]


class AuditHeadResponse(BaseModel):
    head: str


class ScopeTokenIssueRequest(BaseModel):
    targets: list[str] = Field(..., min_length=1)
    permits: list[ScopeAction] = Field(..., min_length=1)
    tier: ScopeTier
    ttl_seconds: int = Field(default=8 * 60 * 60, gt=0, le=24 * 60 * 60)
    rules_of_engagement: str = ""


class ScopeTokenIssueResponse(BaseModel):
    token: str
    jti: str
    engagement_id: str
    expires_at: int


class ScopeTokenRevokeRequest(BaseModel):
    jti: str = Field(..., min_length=1)


class ProvisionRequest(BaseModel):
    template: str = Field(..., min_length=1)


class ProvisionVMsResponse(BaseModel):
    engagement_id: str
    vms: list[ProvisionedVM]


class TeardownResponse(BaseModel):
    engagement_id: str
    vms_destroyed: int
    network_destroyed: int


@router.post(
    "/start",
    response_model=EngagementStartResponse,
    status_code=status.HTTP_201_CREATED,
)
async def engagement_start(req: EngagementStartRequest) -> EngagementStartResponse:
    head_before = get_audit_chain().head()
    engagement = store.create(
        slug=req.slug,
        purpose=req.purpose,
        scope=req.scope,
        audit_head_at_open=head_before,
    )
    token, jti, exp = issue_scope_token(engagement_id=engagement.id, scope=req.scope)
    store.attach_jti(engagement.id, jti, tier=req.scope.tier, expires_at=exp)
    emit_audit(
        "engagement_start",
        engagement_id=engagement.id,
        jti=jti,
    )
    return EngagementStartResponse(
        engagement_id=engagement.id,
        scope_token=token,
        jti=jti,
        expires_at=exp,
        status=engagement.status,
    )


@router.get("", response_model=EngagementListResponse)
async def engagement_list() -> EngagementListResponse:
    return EngagementListResponse(engagements=store.list())


@router.get("/{engagement_id}", response_model=EngagementStatusResponse)
async def engagement_status(engagement_id: str) -> EngagementStatusResponse:
    engagement = store.get(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    return EngagementStatusResponse(engagement=engagement)


@router.get("/{engagement_id}/issued-tokens", response_model=IssuedTokensResponse)
async def engagement_issued_tokens(engagement_id: str) -> IssuedTokensResponse:
    engagement = store.get(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    return IssuedTokensResponse(jtis=engagement.issued_jtis)


@router.get("/{engagement_id}/audit-head", response_model=AuditHeadResponse)
async def engagement_audit_head(engagement_id: str) -> AuditHeadResponse:
    if store.get(engagement_id) is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    return AuditHeadResponse(head=get_audit_chain().head())


@router.post("/{engagement_id}/close", response_model=EngagementStatusResponse)
async def engagement_close(engagement_id: str) -> EngagementStatusResponse:
    engagement = store.close(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    emit_audit("engagement_close", engagement_id=engagement_id)
    return EngagementStatusResponse(engagement=engagement)


@router.post("/{engagement_id}/erase", response_model=EngagementStatusResponse)
async def engagement_erase(engagement_id: str) -> EngagementStatusResponse:
    existing = store.get(engagement_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    if existing.status == EngagementStatus.erased:
        return EngagementStatusResponse(engagement=existing)

    if existing.status == EngagementStatus.active:
        store.close(engagement_id)
        emit_audit("engagement_close", engagement_id=engagement_id)

    try:
        provisioner.teardown(engagement_id)
    except ProvisionError as exc:  # pragma: no cover — substrate down
        emit_audit(
            "engagement_teardown_failed",
            engagement_id=engagement_id,
            reason=exc.reason,
        )

    emit_audit("engagement_erased", engagement_id=engagement_id)
    head_after = get_audit_chain().head()

    erased = store.erase(engagement_id, audit_head_at_close=head_after)
    if erased is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    return EngagementStatusResponse(engagement=erased)


@router.post(
    "/{engagement_id}/scope-token",
    response_model=ScopeTokenIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_scope_token_endpoint(
    engagement_id: str, req: ScopeTokenIssueRequest
) -> ScopeTokenIssueResponse:
    engagement = store.get(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    if engagement.status != EngagementStatus.active:
        raise HTTPException(status_code=409, detail=f"engagement is {engagement.status.value}")

    scope = ScopeDocument(
        allowed_cidrs=req.targets,
        allowed_actions=req.permits,
        tier=req.tier,
        rules_of_engagement=req.rules_of_engagement or engagement.scope.rules_of_engagement,
        expires_at=int(time.time()) + req.ttl_seconds,
    )
    token, jti, exp = issue_scope_token(engagement_id=engagement_id, scope=scope)
    store.attach_jti(engagement_id, jti, tier=scope.tier, expires_at=exp)
    emit_audit(
        "scope_token_issued",
        engagement_id=engagement_id,
        jti=jti,
        tier=scope.tier,
    )
    return ScopeTokenIssueResponse(
        token=token,
        jti=jti,
        engagement_id=engagement_id,
        expires_at=exp,
    )


@router.post(
    "/{engagement_id}/scope-token/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_scope_token(engagement_id: str, req: ScopeTokenRevokeRequest) -> None:
    if store.get(engagement_id) is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    get_revocation_store().revoke(req.jti)
    emit_audit(
        "scope_token_revoked",
        engagement_id=engagement_id,
        jti=req.jti,
    )


@router.post(
    "/{engagement_id}/provision",
    response_model=ProvisionResult,
    status_code=status.HTTP_201_CREATED,
)
async def provision_engagement(
    engagement_id: str, req: ProvisionRequest
) -> ProvisionResult:
    try:
        loaded = load_template_by_name(req.template)
    except TemplateValidationError as exc:
        raise HTTPException(
            status_code=404, detail=f"template_invalid:{exc.reason}"
        ) from exc
    try:
        result = provisioner.provision(engagement_id=engagement_id, template=loaded)
    except ProvisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    return result


@router.post(
    "/{engagement_id}/teardown",
    response_model=TeardownResponse,
)
async def teardown_engagement(engagement_id: str) -> TeardownResponse:
    if store.get(engagement_id) is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    counts = provisioner.teardown(engagement_id)
    return TeardownResponse(
        engagement_id=engagement_id,
        vms_destroyed=counts["vms_destroyed"],
        network_destroyed=counts["network_destroyed"],
    )


@router.get("/{engagement_id}/vms", response_model=ProvisionVMsResponse)
async def list_engagement_vms(engagement_id: str) -> ProvisionVMsResponse:
    if store.get(engagement_id) is None:
        raise HTTPException(status_code=404, detail="engagement not found")
    return ProvisionVMsResponse(
        engagement_id=engagement_id, vms=provisioner.list_vms(engagement_id)
    )
