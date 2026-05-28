from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...lib.audit import emit_audit
from ...lib.engagements import EngagementStatus, EngagementStore
from ...lib.forks import (
    DecisionFork,
    ForkError,
    ForkStatus,
    get_fork_broadcaster,
    get_fork_store,
)
from ...lib.templates import ForkType

router = APIRouter()
store = get_fork_store()
engagement_store = EngagementStore()
broadcaster = get_fork_broadcaster()


class ForkOpenRequest(BaseModel):
    fork_type: ForkType
    prompt: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class ForkResolveRequest(BaseModel):
    resolution: Literal["approved", "denied"]
    operator: str = Field(..., min_length=1)
    rationale: str = ""


class ForkResponse(BaseModel):
    fork: DecisionFork


class ForkListResponse(BaseModel):
    forks: list[DecisionFork]


def _ensure_engagement_active(engagement_id: str) -> None:
    engagement = engagement_store.get(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="engagement_not_found")
    if engagement.status != EngagementStatus.active:
        raise HTTPException(
            status_code=409, detail=f"engagement_{engagement.status.value}"
        )


@router.post("/{engagement_id}/forks", response_model=ForkResponse, status_code=201)
async def open_fork(engagement_id: str, req: ForkOpenRequest) -> ForkResponse:
    _ensure_engagement_active(engagement_id)
    try:
        fork = await store.open_async(
            engagement_id=engagement_id,
            fork_type=req.fork_type,
            prompt=req.prompt,
            context=req.context,
        )
    except ForkError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    emit_audit(
        "decision_fork_opened",
        engagement_id=engagement_id,
        fork_id=fork.id,
        fork_type=fork.fork_type,
    )
    return ForkResponse(fork=fork)


@router.post("/forks/{fork_id}/resolve", response_model=ForkResponse)
async def resolve_fork(fork_id: str, req: ForkResolveRequest) -> ForkResponse:
    try:
        fork = await store.resolve_async(
            fork_id,
            resolution=req.resolution,
            operator=req.operator,
            rationale=req.rationale,
        )
    except ForkError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    emit_audit(
        "decision_fork_resolved",
        engagement_id=fork.engagement_id,
        fork_id=fork.id,
        resolution=fork.resolution or "",
        operator=fork.resolved_by or "",
    )
    return ForkResponse(fork=fork)


@router.get("/{engagement_id}/forks", response_model=ForkListResponse)
async def list_forks(
    engagement_id: str,
    status: ForkStatus | None = None,
) -> ForkListResponse:
    if engagement_store.get(engagement_id) is None:
        raise HTTPException(status_code=404, detail="engagement_not_found")
    return ForkListResponse(forks=store.list(engagement_id, status=status))


@router.get("/{engagement_id}/forks/stream")
async def stream_forks(engagement_id: str) -> StreamingResponse:
    if engagement_store.get(engagement_id) is None:
        raise HTTPException(status_code=404, detail="engagement_not_found")

    async def event_source() -> Any:
        # Replay current open forks first so a late subscriber sees pending state.
        for fork in store.list(engagement_id, status="open"):
            yield _format_event(
                "opened", {"event": "opened", "fork": fork.model_dump()}
            )
        yield ":heartbeat\n\n"

        async with broadcaster.subscribe(engagement_id) as queue:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield _format_event(event.get("event", "event"), event)
                except TimeoutError:
                    yield ":heartbeat\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")


def _format_event(event_type: str, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"
