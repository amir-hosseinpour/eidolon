from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "eidolon-orchestrator"


def _sample_scope() -> dict:
    return {
        "allowed_cidrs": ["10.10.0.0/16"],
        "allowed_actions": ["recon.read", "recon.active"],
        "tier": "autonomous",
        "rules_of_engagement": "defcon demo",
    }


def test_engagement_lifecycle(client: TestClient) -> None:
    resp = client.post(
        "/v1/engagements/start",
        json={
            "slug": "defcon-demo",
            "purpose": "ctf",
            "scope": _sample_scope(),
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    engagement_id = body["engagement_id"]
    assert body["status"] == "active"
    assert body["scope_token"]
    assert body["jti"]

    status = client.get(f"/v1/engagements/{engagement_id}").json()
    assert status["engagement"]["id"] == engagement_id
    assert status["engagement"]["status"] == "active"

    closed = client.post(f"/v1/engagements/{engagement_id}/close").json()
    assert closed["engagement"]["status"] == "closed"


def test_tool_dispatch_requires_scope_token(client: TestClient) -> None:
    resp = client.post(
        "/v1/tools/dispatch",
        json={
            "engagement_id": "ENG-fake",
            "tool_id": "recon.nmap.tcp-top-1000",
            "action": "recon.active",
            "target": "10.10.1.5",
        },
    )
    assert resp.status_code == 422


def test_tool_dispatch_rejects_out_of_scope_target(client: TestClient) -> None:
    start = client.post(
        "/v1/engagements/start",
        json={
            "slug": "scope-test",
            "purpose": "research",
            "scope": _sample_scope(),
        },
    ).json()
    token = start["scope_token"]
    engagement_id = start["engagement_id"]

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
