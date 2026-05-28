from __future__ import annotations

from fastapi import Header, HTTPException

from ..lib.scope import ScopeError, VerifiedToken, verify_scope_token


async def require_scope_token(
    engagement_id: str,
    x_scope_token: str = Header(...),
) -> VerifiedToken:
    try:
        return verify_scope_token(x_scope_token, expected_engagement=engagement_id)
    except ScopeError as e:
        raise HTTPException(status_code=e.status_code, detail={"reason": e.reason}) from e
