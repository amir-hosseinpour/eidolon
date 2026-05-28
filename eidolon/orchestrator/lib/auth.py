from __future__ import annotations

import hmac
import os
import secrets
import threading
from pathlib import Path

from fastapi import Header, HTTPException, status

_TOKEN_FILE = "orchestrator-token"  # noqa: S105 — filename, not a credential
_lock = threading.Lock()


def _eidolon_home() -> Path:
    override = os.environ.get("EIDOLON_HOME")
    if override:
        return Path(override)
    return Path.home() / ".eidolon"


def token_path() -> Path:
    return _eidolon_home() / _TOKEN_FILE


def _write_token(value: str) -> None:
    p = token_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(p.parent, 0o700)
    p.write_text(value)
    os.chmod(p, 0o600)


def generate_token() -> str:
    """Generate a new 32-byte hex token, persist with mode 0600, return it."""
    with _lock:
        token = secrets.token_hex(32)
        _write_token(token)
        return token


def load_token() -> str | None:
    """Return the persisted token, or None if not initialized."""
    p = token_path()
    if not p.exists():
        return None
    return p.read_text().strip() or None


def load_or_create_token() -> str:
    """Read the token; create one if absent. Used for lazy dev/test bootstrap."""
    existing = load_token()
    if existing:
        return existing
    return generate_token()


def rotate_token() -> str:
    """Generate a new token, replacing any existing one."""
    return generate_token()


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    expected = load_or_create_token()
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "missing_authorization"},
        )
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "bad_authorization"},
        )
    if not hmac.compare_digest(parts[1], expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason": "bad_token"},
        )
