from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from eidolon.orchestrator.lib.audit import AuditChain, reset_audit_chain


@pytest.fixture(autouse=True)
def _reset_chain():
    reset_audit_chain()
    yield
    reset_audit_chain()


def _sample_scope() -> dict:
    return {
        "allowed_cidrs": ["10.10.0.0/16"],
        "allowed_actions": ["recon.read"],
        "tier": "autonomous",
        "rules_of_engagement": "test",
    }


def _open(client: TestClient, slug: str = "erase-test") -> str:
    resp = client.post(
        "/v1/engagements/start",
        json={"slug": slug, "purpose": "research", "scope": _sample_scope()},
    )
    assert resp.status_code == 201
    return resp.json()["engagement_id"]


def test_erase_open_engagement_transitions_to_erased(client: TestClient) -> None:
    engagement_id = _open(client)

    resp = client.post(f"/v1/engagements/{engagement_id}/erase")
    assert resp.status_code == 200
    eng = resp.json()["engagement"]
    assert eng["id"] == engagement_id
    assert eng["status"] == "erased"
    assert eng["closed_at"] is not None
    assert eng["erased_at"] is not None
    assert eng["erased_at"] >= eng["closed_at"] >= eng["created_at"]


def test_erase_is_idempotent(client: TestClient) -> None:
    engagement_id = _open(client, slug="erase-replay")

    first = client.post(f"/v1/engagements/{engagement_id}/erase").json()
    second = client.post(f"/v1/engagements/{engagement_id}/erase").json()

    assert first == second


def test_erase_unknown_engagement_returns_404(client: TestClient) -> None:
    resp = client.post("/v1/engagements/ENG-does-not-exist/erase")
    assert resp.status_code == 404


def test_erase_after_explicit_close(client: TestClient) -> None:
    engagement_id = _open(client, slug="erase-after-close")
    client.post(f"/v1/engagements/{engagement_id}/close")

    resp = client.post(f"/v1/engagements/{engagement_id}/erase")
    assert resp.status_code == 200
    eng = resp.json()["engagement"]
    assert eng["status"] == "erased"


def test_audit_head_endpoint_returns_live_head(client: TestClient) -> None:
    engagement_id = _open(client, slug="audit-head")
    resp = client.get(f"/v1/engagements/{engagement_id}/audit-head")
    assert resp.status_code == 200
    head = resp.json()["head"]
    assert head != "0" * 64
    assert head == AuditChain().head()


def test_erase_records_audit_head_at_close(client: TestClient) -> None:
    _open(client, slug="audit-head-warmup")
    engagement_id = _open(client, slug="audit-head-anchor")
    client.post(
        f"/v1/engagements/{engagement_id}/scope-token",
        json={
            "targets": ["10.0.0.0/24"],
            "permits": ["recon.read"],
            "tier": "autonomous",
            "ttl_seconds": 3600,
        },
    )
    state = client.get(f"/v1/engagements/{engagement_id}").json()["engagement"]
    head_at_open = state["audit_head_at_open"]
    assert head_at_open != "0" * 64

    erased = client.post(f"/v1/engagements/{engagement_id}/erase").json()["engagement"]
    assert erased["audit_head_at_open"] == head_at_open
    assert erased["audit_head_at_close"] == AuditChain().head()
    assert erased["audit_head_at_close"] != head_at_open


def test_issued_tokens_lists_jtis(client: TestClient) -> None:
    engagement_id = _open(client, slug="tokens-list")
    client.post(
        f"/v1/engagements/{engagement_id}/scope-token",
        json={
            "targets": ["10.0.0.0/24"],
            "permits": ["recon.read"],
            "tier": "autonomous",
            "ttl_seconds": 3600,
        },
    )
    resp = client.get(f"/v1/engagements/{engagement_id}/issued-tokens")
    assert resp.status_code == 200
    jtis = resp.json()["jtis"]
    assert len(jtis) == 2
