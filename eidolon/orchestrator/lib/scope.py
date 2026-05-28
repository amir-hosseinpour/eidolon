from __future__ import annotations

import ipaddress
import time
import uuid
from dataclasses import dataclass
from typing import Literal

import jwt
from pydantic import BaseModel, Field, field_validator

from .config import get_settings
from .revocation import get_revocation_store

ScopeAction = Literal[
    "recon.read",
    "recon.active",
    "exploit.send",
    "crack.offline",
    "sandbox.exec",
    "report.read",
]

ScopeTier = Literal["autonomous", "confirm", "prohibited"]

_TIER_ORDER: dict[ScopeTier, int] = {
    "autonomous": 0,
    "confirm": 1,
    "prohibited": 2,
}


class ScopeError(Exception):
    """Raised when scope verification fails. Carries the HTTP status and stable reason."""

    def __init__(self, status_code: int, reason: str) -> None:
        super().__init__(f"{status_code} {reason}")
        self.status_code = status_code
        self.reason = reason


class ScopeDocument(BaseModel):
    allowed_cidrs: list[str] = Field(default_factory=list)
    allowed_actions: list[ScopeAction] = Field(default_factory=list)
    tier: ScopeTier = "autonomous"
    rules_of_engagement: str = ""
    expires_at: int | None = None

    @field_validator("allowed_cidrs")
    @classmethod
    def _validate_cidrs(cls, values: list[str]) -> list[str]:
        for entry in values:
            ipaddress.ip_network(entry, strict=False)
        return values

    def covers_target(self, target_ip: str) -> bool:
        if not self.allowed_cidrs:
            return False
        ip = ipaddress.ip_address(target_ip)
        for cidr in self.allowed_cidrs:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
        return False

    def permits(self, action: ScopeAction) -> bool:
        return action in self.allowed_actions

    def admits_tier(self, requested: ScopeTier) -> bool:
        return _TIER_ORDER[requested] <= _TIER_ORDER[self.tier]


@dataclass(frozen=True)
class VerifiedToken:
    engagement_id: str
    jti: str
    scope: ScopeDocument
    iat: int
    exp: int


def issue_scope_token(engagement_id: str, scope: ScopeDocument) -> tuple[str, str, int]:
    """Issue an HS256 token bound to the engagement. Returns (token, jti, exp)."""
    settings = get_settings()
    now = int(time.time())
    exp = scope.expires_at or (now + settings.scope_token_ttl_seconds)
    jti = str(uuid.uuid4())
    payload = {
        "sub": engagement_id,
        "jti": jti,
        "iat": now,
        "exp": exp,
        "scope": scope.model_dump(),
    }
    token = jwt.encode(payload, settings.hmac_secret, algorithm="HS256")
    return token, jti, exp


def verify_scope_token(
    token: str,
    *,
    expected_engagement: str | None = None,
    target: str | None = None,
    action: ScopeAction | None = None,
    requested_tier: ScopeTier | None = None,
) -> VerifiedToken:
    """Verify a scope token end to end.

    Order of checks: signature -> engagement match -> revocation -> (expiry handled
    by PyJWT) -> CIDR target -> action -> tier. Raises ScopeError on failure.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.hmac_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise ScopeError(401, "token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ScopeError(401, "token_invalid") from exc

    engagement_id = payload.get("sub")
    jti = payload.get("jti")
    if not engagement_id or not jti:
        raise ScopeError(401, "token_invalid")

    if expected_engagement is not None and engagement_id != expected_engagement:
        raise ScopeError(403, "engagement_mismatch")

    if get_revocation_store().is_revoked(jti):
        raise ScopeError(401, "token_revoked")

    try:
        scope = ScopeDocument.model_validate(payload["scope"])
    except Exception as exc:
        raise ScopeError(401, "token_invalid") from exc

    if target is not None and not scope.covers_target(target):
        raise ScopeError(403, "target_out_of_scope")
    if action is not None and not scope.permits(action):
        raise ScopeError(403, "action_out_of_scope")
    if requested_tier is not None and not scope.admits_tier(requested_tier):
        raise ScopeError(403, "tier_exceeded")

    return VerifiedToken(
        engagement_id=engagement_id,
        jti=jti,
        scope=scope,
        iat=int(payload["iat"]),
        exp=int(payload["exp"]),
    )
