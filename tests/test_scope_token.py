from __future__ import annotations

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from eidolon.orchestrator.lib.revocation import get_revocation_store


def _scope_doc(
    *,
    cidrs: list[str] | None = None,
    actions: list[str] | None = None,
    tier: str = "autonomous",
) -> dict:
    return {
        "allowed_cidrs": cidrs or ["10.10.0.0/16"],
        "allowed_actions": actions or ["recon.read", "recon.active"],
        "tier": tier,
        "rules_of_engagement": "test",
    }


def _start_engagement(client: TestClient, **scope_kwargs) -> tuple[str, str]:
    resp = client.post(
        "/v1/engagements/start",
        json={
            "slug": "spec-001",
            "purpose": "ctf",
            "scope": _scope_doc(**scope_kwargs),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["engagement_id"], body["scope_token"]


@pytest.fixture(autouse=True)
def _clear_revocations() -> None:
    get_revocation_store().reset()
    yield
    get_revocation_store().reset()


def test_issue_scope_token_returns_token_jti_engagement_id_exp(client: TestClient) -> None:
    engagement_id, _ = _start_engagement(client)
    resp = client.post(
        f"/v1/engagements/{engagement_id}/scope-token",
        json={
            "targets": ["10.0.0.0/24"],
            "permits": ["recon.active"],
            "tier": "confirm",
            "ttl_seconds": 300,
            "rules_of_engagement": "AC-1",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["engagement_id"] == engagement_id
    assert body["jti"]
    assert body["expires_at"] > int(time.time())
    assert body["token"]


def test_revoke_then_verify_returns_401_token_revoked(client: TestClient) -> None:
    engagement_id, _ = _start_engagement(client)
    issued = client.post(
        f"/v1/engagements/{engagement_id}/scope-token",
        json={
            "targets": ["10.10.0.0/16"],
            "permits": ["recon.active"],
            "tier": "autonomous",
            "ttl_seconds": 300,
        },
    ).json()
    token = issued["token"]
    jti = issued["jti"]

    revoke = client.post(
        f"/v1/engagements/{engagement_id}/scope-token/revoke",
        json={"jti": jti},
    )
    assert revoke.status_code == 204

    resp = client.post(
        "/v1/tools/dispatch",
        json={
            "engagement_id": engagement_id,
            "tool_id": "recon.nmap.tcp-top-1000",
            "action": "recon.active",
            "target": "10.10.1.5",
        },
        headers={"x-scope-token": token},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["reason"] == "token_revoked"


def test_verify_rejects_token_invalid_signature(client: TestClient) -> None:
    engagement_id, _ = _start_engagement(client)
    bad = jwt.encode(
        {
            "sub": engagement_id,
            "jti": "x",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "scope": _scope_doc(),
        },
        "wrong-key-wrong-key-wrong-key-wrong-key!",
        algorithm="HS256",
    )
    resp = client.post(
        "/v1/tools/dispatch",
        json={
            "engagement_id": engagement_id,
            "tool_id": "recon.nmap.tcp-top-1000",
            "action": "recon.active",
            "target": "10.10.1.5",
        },
        headers={"x-scope-token": bad},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["reason"] == "token_invalid"


def test_verify_rejects_token_expired(client: TestClient, monkeypatch) -> None:
    from eidolon.orchestrator.lib.config import get_settings

    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": "ENG-x",
            "jti": "j",
            "iat": int(time.time()) - 1000,
            "exp": int(time.time()) - 100,
            "scope": _scope_doc(),
        },
        settings.hmac_secret,
        algorithm="HS256",
    )
    engagement_id, _ = _start_engagement(client)
    resp = client.post(
        "/v1/tools/dispatch",
        json={
            "engagement_id": engagement_id,
            "tool_id": "recon.nmap.tcp-top-1000",
            "action": "recon.active",
            "target": "10.10.1.5",
        },
        headers={"x-scope-token": expired},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["reason"] == "token_expired"


def test_verify_rejects_engagement_mismatch(client: TestClient) -> None:
    engagement_a, token_a = _start_engagement(client)
    engagement_b, _ = _start_engagement(client)
    resp = client.post(
        "/v1/tools/dispatch",
        json={
            "engagement_id": engagement_b,
            "tool_id": "recon.nmap.tcp-top-1000",
            "action": "recon.active",
            "target": "10.10.1.5",
        },
        headers={"x-scope-token": token_a},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "engagement_mismatch"


def test_verify_rejects_target_out_of_scope(client: TestClient) -> None:
    engagement_id, token = _start_engagement(client, cidrs=["10.10.0.0/16"])
    resp = client.post(
        "/v1/tools/dispatch",
        json={
            "engagement_id": engagement_id,
            "tool_id": "recon.nmap.tcp-top-1000",
            "action": "recon.active",
            "target": "8.8.8.8",
        },
        headers={"x-scope-token": token},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "target_out_of_scope"


def test_verify_rejects_action_out_of_scope(client: TestClient) -> None:
    engagement_id, token = _start_engagement(client, actions=["recon.read"])
    resp = client.post(
        "/v1/tools/dispatch",
        json={
            "engagement_id": engagement_id,
            "tool_id": "recon.nmap.tcp-top-1000",
            "action": "recon.active",
            "target": "10.10.1.5",
        },
        headers={"x-scope-token": token},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "action_out_of_scope"


def test_verify_rejects_tier_exceeded(client: TestClient) -> None:
    engagement_id, token = _start_engagement(client, tier="autonomous")
    resp = client.post(
        "/v1/tools/dispatch",
        json={
            "engagement_id": engagement_id,
            "tool_id": "recon.nmap.full",
            "action": "recon.active",
            "target": "10.10.1.5",
        },
        headers={"x-scope-token": token, "x-confirm-token": "yes"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "tier_exceeded"


def test_cidr_boundary_rejects_one_bit_outside(client: TestClient) -> None:
    engagement_id, token = _start_engagement(client, cidrs=["10.0.0.0/24"])
    resp = client.post(
        "/v1/tools/dispatch",
        json={
            "engagement_id": engagement_id,
            "tool_id": "recon.nmap.tcp-top-1000",
            "action": "recon.active",
            "target": "10.0.1.1",
        },
        headers={"x-scope-token": token},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["reason"] == "target_out_of_scope"


@pytest.mark.parametrize(
    "token_tier,tool_id,expected_status",
    [
        ("autonomous", "recon.nmap.tcp-top-1000", 200),
        ("autonomous", "recon.nmap.full", 403),
        ("autonomous", "exploit.ransomware.deploy", 403),
        ("confirm", "recon.nmap.tcp-top-1000", 200),
        ("confirm", "recon.nmap.full", 200),
        ("confirm", "exploit.ransomware.deploy", 403),
        ("prohibited", "recon.nmap.tcp-top-1000", 200),
        ("prohibited", "recon.nmap.full", 200),
        ("prohibited", "exploit.ransomware.deploy", 403),
    ],
)
def test_tier_ordering(
    client: TestClient,
    token_tier: str,
    tool_id: str,
    expected_status: int,
) -> None:
    engagement_id, token = _start_engagement(
        client,
        actions=["recon.active", "exploit.send"],
        tier=token_tier,
    )
    resp = client.post(
        "/v1/tools/dispatch",
        json={
            "engagement_id": engagement_id,
            "tool_id": tool_id,
            "action": "recon.active" if "recon" in tool_id else "exploit.send",
            "target": "10.10.1.5",
            "confirm_token": "yes",
        },
        headers={"x-scope-token": token},
    )
    assert resp.status_code == expected_status, resp.text


def test_issuance_on_closed_engagement_returns_409(client: TestClient) -> None:
    engagement_id, _ = _start_engagement(client)
    client.post(f"/v1/engagements/{engagement_id}/close")
    resp = client.post(
        f"/v1/engagements/{engagement_id}/scope-token",
        json={
            "targets": ["10.0.0.0/24"],
            "permits": ["recon.active"],
            "tier": "autonomous",
            "ttl_seconds": 60,
        },
    )
    assert resp.status_code == 409
