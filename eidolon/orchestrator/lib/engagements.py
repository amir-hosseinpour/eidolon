from __future__ import annotations

import json
import secrets
import sqlite3
import time
from enum import StrEnum

from pydantic import BaseModel, Field

from .audit import ZERO_HASH
from .db import get_db, write_tx
from .scope import ScopeDocument


class EngagementStatus(StrEnum):
    active = "active"
    closed = "closed"
    erased = "erased"


class Engagement(BaseModel):
    id: str
    slug: str
    purpose: str
    status: EngagementStatus
    scope: ScopeDocument
    created_at: int
    closed_at: int | None = None
    erased_at: int | None = None
    notes: list[str] = Field(default_factory=list)
    issued_jtis: list[str] = Field(default_factory=list)
    audit_head_at_open: str = ZERO_HASH
    audit_head_at_close: str | None = None


def _row_to_engagement(row: sqlite3.Row, jtis: list[str]) -> Engagement:
    return Engagement(
        id=row["id"],
        slug=row["slug"],
        purpose=row["purpose"],
        status=EngagementStatus(row["status"]),
        scope=ScopeDocument.model_validate_json(row["scope_json"]),
        created_at=row["created_at"],
        closed_at=row["closed_at"],
        erased_at=row["erased_at"],
        notes=json.loads(row["notes_json"]),
        issued_jtis=jtis,
        audit_head_at_open=row["audit_head_at_open"],
        audit_head_at_close=row["audit_head_at_close"],
    )


def _load_jtis(conn: sqlite3.Connection, engagement_id: str) -> list[str]:
    cur = conn.execute(
        "SELECT jti FROM scope_tokens WHERE engagement_id = ? ORDER BY issued_at ASC",
        (engagement_id,),
    )
    return [r["jti"] for r in cur.fetchall()]


class EngagementStore:
    """SQLite-backed engagement store. Process-safe within a single host."""

    def create(
        self,
        *,
        slug: str,
        purpose: str,
        scope: ScopeDocument,
        audit_head_at_open: str = ZERO_HASH,
    ) -> Engagement:
        engagement_id = f"ENG-{int(time.time())}-{secrets.token_hex(3)}"
        now = int(time.time())
        with write_tx() as conn:
            conn.execute(
                """
                INSERT INTO engagements (
                    id, slug, purpose, status, scope_json,
                    created_at, audit_head_at_open, notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '[]')
                """,
                (
                    engagement_id,
                    slug,
                    purpose,
                    EngagementStatus.active.value,
                    scope.model_dump_json(),
                    now,
                    audit_head_at_open,
                ),
            )
        return Engagement(
            id=engagement_id,
            slug=slug,
            purpose=purpose,
            status=EngagementStatus.active,
            scope=scope,
            created_at=now,
            audit_head_at_open=audit_head_at_open,
        )

    def get(self, engagement_id: str) -> Engagement | None:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM engagements WHERE id = ?", (engagement_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_engagement(row, _load_jtis(conn, engagement_id))

    def close(self, engagement_id: str) -> Engagement | None:
        with write_tx() as conn:
            row = conn.execute(
                "SELECT * FROM engagements WHERE id = ?", (engagement_id,)
            ).fetchone()
            if row is None:
                return None
            if row["status"] != EngagementStatus.active.value:
                return _row_to_engagement(row, _load_jtis(conn, engagement_id))
            now = int(time.time())
            conn.execute(
                "UPDATE engagements SET status = ?, closed_at = ? WHERE id = ?",
                (EngagementStatus.closed.value, now, engagement_id),
            )
            row = conn.execute(
                "SELECT * FROM engagements WHERE id = ?", (engagement_id,)
            ).fetchone()
            return _row_to_engagement(row, _load_jtis(conn, engagement_id))

    def attach_jti(
        self,
        engagement_id: str,
        jti: str,
        *,
        tier: str,
        expires_at: int,
    ) -> None:
        now = int(time.time())
        with write_tx() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO scope_tokens (
                    jti, engagement_id, tier, issued_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (jti, engagement_id, tier, now, expires_at),
            )

    def erase(
        self,
        engagement_id: str,
        *,
        audit_head_at_close: str,
    ) -> Engagement | None:
        with write_tx() as conn:
            row = conn.execute(
                "SELECT * FROM engagements WHERE id = ?", (engagement_id,)
            ).fetchone()
            if row is None:
                return None
            if row["status"] == EngagementStatus.erased.value:
                return _row_to_engagement(row, _load_jtis(conn, engagement_id))
            now = int(time.time())
            closed_at = row["closed_at"] or now
            conn.execute(
                """
                UPDATE engagements
                SET status = ?, closed_at = ?, erased_at = ?, audit_head_at_close = ?
                WHERE id = ?
                """,
                (
                    EngagementStatus.erased.value,
                    closed_at,
                    now,
                    audit_head_at_close,
                    engagement_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM engagements WHERE id = ?", (engagement_id,)
            ).fetchone()
            return _row_to_engagement(row, _load_jtis(conn, engagement_id))

    def list(self) -> list[Engagement]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM engagements ORDER BY created_at ASC"
        ).fetchall()
        return [_row_to_engagement(r, _load_jtis(conn, r["id"])) for r in rows]

    def reset(self) -> None:
        with write_tx() as conn:
            conn.execute("DELETE FROM dispatches")
            conn.execute("DELETE FROM scope_tokens")
            conn.execute("DELETE FROM engagements")
