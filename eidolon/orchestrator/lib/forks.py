from __future__ import annotations

import asyncio
import json
import secrets
import sqlite3
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from pydantic import BaseModel, Field

from .db import get_db, write_tx
from .templates import ForkType

ForkStatus = Literal["open", "approved", "denied", "expired"]


class ForkError(Exception):
    """Raised on a decision-fork operation failure."""

    def __init__(self, status_code: int, reason: str) -> None:
        super().__init__(f"{status_code} {reason}")
        self.status_code = status_code
        self.reason = reason


class DecisionFork(BaseModel):
    id: str
    engagement_id: str
    fork_type: ForkType
    status: ForkStatus
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: int
    resolved_at: int | None = None
    resolved_by: str | None = None
    resolution: str | None = None
    rationale: str | None = None


def _row_to_fork(row: sqlite3.Row) -> DecisionFork:
    return DecisionFork(
        id=row["id"],
        engagement_id=row["engagement_id"],
        fork_type=row["fork_type"],
        status=row["status"],
        prompt=row["prompt"],
        context=json.loads(row["context_json"]) if row["context_json"] else {},
        created_at=row["created_at"],
        resolved_at=row["resolved_at"],
        resolved_by=row["resolved_by"],
        resolution=row["resolution"],
        rationale=row["rationale"],
    )


class ForkBroadcaster:
    """In-process pub/sub for fork lifecycle events, keyed by engagement_id.

    The orchestrator is single-process for v0.1; SSE listeners attach via
    `subscribe()` and receive every published event for the given engagement
    until they unsubscribe. Buffer is bounded to drop slow clients rather
    than OOM the orchestrator.
    """

    BUFFER_PER_LISTENER = 256

    def __init__(self) -> None:
        self._listeners: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, engagement_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._listeners.get(engagement_id, ()))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer; drop the event for that listener only.
                pass

    @asynccontextmanager
    async def subscribe(
        self, engagement_id: str
    ) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.BUFFER_PER_LISTENER)
        async with self._lock:
            self._listeners[engagement_id].add(q)
        try:
            yield q
        finally:
            async with self._lock:
                self._listeners[engagement_id].discard(q)
                if not self._listeners[engagement_id]:
                    del self._listeners[engagement_id]


_broadcaster = ForkBroadcaster()


def get_fork_broadcaster() -> ForkBroadcaster:
    return _broadcaster


class ForkStore:
    """SQLite-backed decision fork store with broadcaster integration."""

    def open(
        self,
        *,
        engagement_id: str,
        fork_type: ForkType,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> DecisionFork:
        if not prompt.strip():
            raise ForkError(400, "prompt_required")
        fork_id = f"FORK-{int(time.time())}-{secrets.token_hex(3)}"
        now = int(time.time())
        ctx = context or {}
        with write_tx() as conn:
            row = conn.execute(
                "SELECT id FROM engagements WHERE id = ?", (engagement_id,)
            ).fetchone()
            if row is None:
                raise ForkError(404, "engagement_not_found")
            conn.execute(
                """
                INSERT INTO forks (
                    id, engagement_id, fork_type, status, prompt,
                    context_json, created_at
                ) VALUES (?, ?, ?, 'open', ?, ?, ?)
                """,
                (fork_id, engagement_id, fork_type, prompt, json.dumps(ctx), now),
            )
        fork = DecisionFork(
            id=fork_id,
            engagement_id=engagement_id,
            fork_type=fork_type,
            status="open",
            prompt=prompt,
            context=ctx,
            created_at=now,
        )
        return fork

    async def open_async(
        self,
        *,
        engagement_id: str,
        fork_type: ForkType,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> DecisionFork:
        fork = self.open(
            engagement_id=engagement_id,
            fork_type=fork_type,
            prompt=prompt,
            context=context,
        )
        await _broadcaster.publish(
            engagement_id, {"event": "opened", "fork": fork.model_dump()}
        )
        return fork

    def resolve(
        self,
        fork_id: str,
        *,
        resolution: Literal["approved", "denied"],
        operator: str,
        rationale: str = "",
    ) -> DecisionFork:
        if not operator.strip():
            raise ForkError(400, "operator_required")
        now = int(time.time())
        with write_tx() as conn:
            row = conn.execute("SELECT * FROM forks WHERE id = ?", (fork_id,)).fetchone()
            if row is None:
                raise ForkError(404, "fork_not_found")
            if row["status"] != "open":
                raise ForkError(409, "fork_not_open")
            conn.execute(
                """
                UPDATE forks
                SET status = ?, resolved_at = ?, resolved_by = ?,
                    resolution = ?, rationale = ?
                WHERE id = ?
                """,
                (resolution, now, operator, resolution, rationale, fork_id),
            )
            row = conn.execute("SELECT * FROM forks WHERE id = ?", (fork_id,)).fetchone()
            return _row_to_fork(row)

    async def resolve_async(
        self,
        fork_id: str,
        *,
        resolution: Literal["approved", "denied"],
        operator: str,
        rationale: str = "",
    ) -> DecisionFork:
        fork = self.resolve(
            fork_id,
            resolution=resolution,
            operator=operator,
            rationale=rationale,
        )
        await _broadcaster.publish(
            fork.engagement_id, {"event": "resolved", "fork": fork.model_dump()}
        )
        return fork

    def get(self, fork_id: str) -> DecisionFork | None:
        conn = get_db()
        row = conn.execute("SELECT * FROM forks WHERE id = ?", (fork_id,)).fetchone()
        return _row_to_fork(row) if row is not None else None

    def list(
        self,
        engagement_id: str,
        *,
        status: ForkStatus | None = None,
    ) -> list[DecisionFork]:
        conn = get_db()
        if status is None:
            rows = conn.execute(
                "SELECT * FROM forks WHERE engagement_id = ? ORDER BY created_at ASC",
                (engagement_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM forks
                WHERE engagement_id = ? AND status = ?
                ORDER BY created_at ASC
                """,
                (engagement_id, status),
            ).fetchall()
        return [_row_to_fork(r) for r in rows]


_store = ForkStore()


def get_fork_store() -> ForkStore:
    return _store
