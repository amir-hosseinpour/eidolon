from __future__ import annotations

import sqlite3
import time

from pydantic import BaseModel

from .db import get_db, write_tx


class DispatchRecord(BaseModel):
    id: str
    engagement_id: str
    jti: str | None
    tool_id: str
    target: str | None
    action: str
    tier: str
    accepted: bool
    reason: str | None
    created_at: int


def _row_to_dispatch(row: sqlite3.Row) -> DispatchRecord:
    return DispatchRecord(
        id=row["id"],
        engagement_id=row["engagement_id"],
        jti=row["jti"],
        tool_id=row["tool_id"],
        target=row["target"],
        action=row["action"],
        tier=row["tier"],
        accepted=bool(row["accepted"]),
        reason=row["reason"],
        created_at=row["created_at"],
    )


class DispatchStore:
    """SQLite-backed record of every /tools/dispatch decision."""

    def record(
        self,
        *,
        dispatch_id: str,
        engagement_id: str,
        jti: str | None,
        tool_id: str,
        target: str | None,
        action: str,
        tier: str,
        accepted: bool,
        reason: str | None,
    ) -> DispatchRecord:
        now = int(time.time())
        with write_tx() as conn:
            conn.execute(
                """
                INSERT INTO dispatches (
                    id, engagement_id, jti, tool_id, target, action,
                    tier, accepted, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dispatch_id,
                    engagement_id,
                    jti,
                    tool_id,
                    target,
                    action,
                    tier,
                    1 if accepted else 0,
                    reason,
                    now,
                ),
            )
        return DispatchRecord(
            id=dispatch_id,
            engagement_id=engagement_id,
            jti=jti,
            tool_id=tool_id,
            target=target,
            action=action,
            tier=tier,
            accepted=accepted,
            reason=reason,
            created_at=now,
        )

    def get(self, dispatch_id: str) -> DispatchRecord | None:
        row = get_db().execute(
            "SELECT * FROM dispatches WHERE id = ?", (dispatch_id,)
        ).fetchone()
        return None if row is None else _row_to_dispatch(row)

    def list_for_engagement(self, engagement_id: str) -> list[DispatchRecord]:
        rows = get_db().execute(
            "SELECT * FROM dispatches WHERE engagement_id = ? ORDER BY created_at ASC",
            (engagement_id,),
        ).fetchall()
        return [_row_to_dispatch(r) for r in rows]

    def reset(self) -> None:
        with write_tx() as conn:
            conn.execute("DELETE FROM dispatches")


_singleton: DispatchStore | None = None


def get_dispatch_store() -> DispatchStore:
    global _singleton
    if _singleton is None:
        _singleton = DispatchStore()
    return _singleton
