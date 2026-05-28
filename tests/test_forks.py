from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from eidolon.orchestrator.lib.engagements import EngagementStore
from eidolon.orchestrator.lib.forks import (
    ForkError,
    get_fork_broadcaster,
    get_fork_store,
)
from eidolon.orchestrator.lib.scope import ScopeDocument


def _make_engagement() -> str:
    store = EngagementStore()
    eng = store.create(
        slug="grill-test",
        purpose="pentest",
        scope=ScopeDocument(
            allowed_cidrs=["10.42.0.0/24"],
            allowed_actions=["recon.read"],
            tier="confirm",
        ),
    )
    return eng.id


def test_open_fork_persists_and_lists() -> None:
    engagement_id = _make_engagement()
    forks = get_fork_store()
    fork = forks.open(
        engagement_id=engagement_id,
        fork_type="scope_edge",
        prompt="Add 10.43.0.0/24 to scope?",
        context={"requested_cidr": "10.43.0.0/24"},
    )
    assert fork.status == "open"
    assert fork.fork_type == "scope_edge"
    listed = forks.list(engagement_id)
    assert len(listed) == 1
    assert listed[0].id == fork.id


def test_open_fork_unknown_engagement_raises() -> None:
    forks = get_fork_store()
    with pytest.raises(ForkError) as exc:
        forks.open(
            engagement_id="ENG-DOES-NOT-EXIST",
            fork_type="scope_edge",
            prompt="x",
        )
    assert exc.value.status_code == 404


def test_resolve_fork_transitions_status() -> None:
    engagement_id = _make_engagement()
    forks = get_fork_store()
    fork = forks.open(
        engagement_id=engagement_id,
        fork_type="noise_threshold",
        prompt="run loud nmap?",
    )
    resolved = forks.resolve(
        fork.id, resolution="approved", operator="damion", rationale="client ok"
    )
    assert resolved.status == "approved"
    assert resolved.resolved_by == "damion"
    assert resolved.rationale == "client ok"


def test_double_resolve_rejected() -> None:
    engagement_id = _make_engagement()
    forks = get_fork_store()
    fork = forks.open(
        engagement_id=engagement_id, fork_type="mode_change", prompt="?"
    )
    forks.resolve(fork.id, resolution="approved", operator="op")
    with pytest.raises(ForkError) as exc:
        forks.resolve(fork.id, resolution="denied", operator="op")
    assert exc.value.status_code == 409


def test_list_filter_by_status() -> None:
    engagement_id = _make_engagement()
    forks = get_fork_store()
    a = forks.open(engagement_id=engagement_id, fork_type="scope_edge", prompt="a")
    b = forks.open(engagement_id=engagement_id, fork_type="scope_edge", prompt="b")
    forks.resolve(a.id, resolution="approved", operator="op")

    open_only = forks.list(engagement_id, status="open")
    approved = forks.list(engagement_id, status="approved")
    assert [f.id for f in open_only] == [b.id]
    assert [f.id for f in approved] == [a.id]


def test_rest_open_and_resolve_flow(client: TestClient) -> None:
    eng_resp = client.post(
        "/v1/engagements/start",
        json={
            "slug": "rest-test",
            "purpose": "pentest",
            "scope": {
                "allowed_cidrs": ["10.42.0.0/24"],
                "allowed_actions": ["recon.read"],
                "tier": "confirm",
            },
        },
    )
    assert eng_resp.status_code == 201, eng_resp.text
    engagement_id = eng_resp.json()["engagement_id"]

    open_resp = client.post(
        f"/v1/engagements/{engagement_id}/forks",
        json={
            "fork_type": "scope_edge",
            "prompt": "add 10.50.0.0/24?",
            "context": {"reason": "pivot path"},
        },
    )
    assert open_resp.status_code == 201, open_resp.text
    fork_id = open_resp.json()["fork"]["id"]

    list_resp = client.get(f"/v1/engagements/{engagement_id}/forks?status=open")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["forks"]) == 1

    resolve_resp = client.post(
        f"/v1/engagements/forks/{fork_id}/resolve",
        json={"resolution": "approved", "operator": "damion", "rationale": "ok"},
    )
    assert resolve_resp.status_code == 200, resolve_resp.text
    body = resolve_resp.json()["fork"]
    assert body["status"] == "approved"
    assert body["resolved_by"] == "damion"


def test_rest_resolve_unknown_fork_404(client: TestClient) -> None:
    resp = client.post(
        "/v1/engagements/forks/FORK-DOES-NOT-EXIST/resolve",
        json={"resolution": "approved", "operator": "op"},
    )
    assert resp.status_code == 404


def test_broadcaster_delivers_events_to_subscribers() -> None:
    engagement_id = _make_engagement()
    forks = get_fork_store()
    bc = get_fork_broadcaster()

    async def runner() -> list[str]:
        async with bc.subscribe(engagement_id) as q:
            opened = await forks.open_async(
                engagement_id=engagement_id,
                fork_type="scope_edge",
                prompt="approve?",
            )
            event_open = await asyncio.wait_for(q.get(), timeout=1.0)
            await forks.resolve_async(
                opened.id, resolution="denied", operator="op"
            )
            event_resolve = await asyncio.wait_for(q.get(), timeout=1.0)
            return [event_open["event"], event_resolve["event"]]

    events = asyncio.run(runner())
    assert events == ["opened", "resolved"]


async def test_sse_event_source_yields_replay_then_heartbeat() -> None:
    """Direct unit test of the SSE event source. Bypasses httpx/starlette
    buffering quirks by exercising the async generator end-to-end against
    a real engagement + fork. Drains exactly the deterministic prefix."""
    from eidolon.orchestrator.app.routers.forks import stream_forks

    engagement_id = _make_engagement()
    forks = get_fork_store()
    forks.open(engagement_id=engagement_id, fork_type="scope_edge", prompt="p1")

    response = await stream_forks(engagement_id)
    body_iter = response.body_iterator

    first = await asyncio.wait_for(body_iter.__anext__(), timeout=1.0)
    second = await asyncio.wait_for(body_iter.__anext__(), timeout=1.0)
    first_str = first.decode() if isinstance(first, bytes) else first
    second_str = second.decode() if isinstance(second, bytes) else second

    assert first_str.startswith("event: opened\n")
    assert "data:" in first_str
    payload_line = next(
        line for line in first_str.splitlines() if line.startswith("data:")
    )
    payload = json.loads(payload_line[len("data:") :].strip())
    assert payload["fork"]["prompt"] == "p1"
    assert second_str.startswith(":heartbeat")
