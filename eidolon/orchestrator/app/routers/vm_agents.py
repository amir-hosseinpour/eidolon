from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ...lib.audit import emit_audit
from ...lib.engagements import EngagementStatus, EngagementStore
from ...lib.secrets import SecretsBroker, SecretsError
from ...lib.vm_agents import VMAgent, VMAgentError, get_vm_agent_store

router = APIRouter()
store = get_vm_agent_store()
engagement_store = EngagementStore()


class RegisterRequest(BaseModel):
    vm_name: str = Field(..., min_length=1)


class RegisterResponse(BaseModel):
    agent: VMAgent


class HeartbeatResponse(BaseModel):
    agent: VMAgent


class SecretRequest(BaseModel):
    label: str = Field(..., min_length=1)


class SecretResponse(BaseModel):
    label: str
    value: str


def _resolve_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_vm_token")
    return authorization[len("Bearer ") :].strip()


def _ensure_active(agent: VMAgent) -> None:
    engagement = engagement_store.get(agent.engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="engagement_not_found")
    if engagement.status != EngagementStatus.active:
        raise HTTPException(
            status_code=409, detail=f"engagement_{engagement.status.value}"
        )


@router.post("/register", response_model=RegisterResponse)
async def register(
    req: RegisterRequest,
    authorization: str | None = Header(default=None),
) -> RegisterResponse:
    vm_token = _resolve_token(authorization)
    try:
        agent = store.register(vm_token, vm_name=req.vm_name)
    except VMAgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    _ensure_active(agent)
    emit_audit(
        "vm_agent_registered",
        engagement_id=agent.engagement_id,
        vm_name=agent.vm_name,
    )
    return RegisterResponse(agent=agent)


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(authorization: str | None = Header(default=None)) -> HeartbeatResponse:
    vm_token = _resolve_token(authorization)
    try:
        agent = store.heartbeat(vm_token)
    except VMAgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    _ensure_active(agent)
    return HeartbeatResponse(agent=agent)


@router.post("/secrets", response_model=SecretResponse)
async def fetch_secret(
    req: SecretRequest,
    authorization: str | None = Header(default=None),
) -> SecretResponse:
    vm_token = _resolve_token(authorization)
    agent = store.lookup(vm_token)
    if agent is None or agent.revoked:
        raise HTTPException(status_code=401, detail="vm_token_invalid")
    _ensure_active(agent)

    try:
        broker = SecretsBroker()
        value = broker.get(req.label)
    except SecretsError as exc:
        raise HTTPException(status_code=400, detail=exc.reason) from exc
    if value is None:
        raise HTTPException(status_code=404, detail="secret_not_found")

    emit_audit(
        "vm_agent_secret_fetched",
        engagement_id=agent.engagement_id,
        vm_name=agent.vm_name,
        label=req.label,
    )
    return SecretResponse(label=req.label, value=value)
