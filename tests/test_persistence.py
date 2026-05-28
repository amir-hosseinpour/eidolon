from __future__ import annotations

from fastapi.testclient import TestClient


def _start_engagement(client: TestClient) -> str:
    body = {
        "slug": "persist-eng",
        "purpose": "pentest",
        "scope": {
            "allowed_cidrs": ["10.0.0.0/24"],
            "allowed_actions": ["recon.read", "recon.active"],
            "tier": "autonomous",
            "rules_of_engagement": "test",
        },
    }
    resp = client.post("/v1/engagements/start", json=body)
    assert resp.status_code == 201
    return resp.json()["engagement_id"]


def test_engagement_survives_app_reload(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Drop the FastAPI app singleton, re-import, the engagement still resolves
    from the same on-disk SQLite state file."""
    engagement_id = _start_engagement(client)

    import importlib

    import eidolon.orchestrator.app.main as main_mod
    import eidolon.orchestrator.app.routers.engagements as eng_mod

    importlib.reload(eng_mod)
    importlib.reload(main_mod)

    fresh_client = TestClient(main_mod.app, headers=auth_headers)
    resp = fresh_client.get(f"/v1/engagements/{engagement_id}")
    assert resp.status_code == 200
    assert resp.json()["engagement"]["id"] == engagement_id
    assert resp.json()["engagement"]["status"] == "active"


def test_dispatch_recorded_in_db(client: TestClient) -> None:
    body = {
        "slug": "disp-eng",
        "purpose": "pentest",
        "scope": {
            "allowed_cidrs": ["10.0.0.0/24"],
            "allowed_actions": ["recon.read"],
            "tier": "autonomous",
        },
    }
    resp = client.post("/v1/engagements/start", json=body)
    assert resp.status_code == 201
    eng_id = resp.json()["engagement_id"]
    token = resp.json()["scope_token"]

    dispatch = client.post(
        "/v1/tools/dispatch",
        json={
            "engagement_id": eng_id,
            "tool_id": "recon.dns.enum",
            "target": "10.0.0.5",
            "action": "recon.read",
        },
        headers={"x-scope-token": token},
    )
    assert dispatch.status_code == 200, dispatch.text
    dispatch_id = dispatch.json()["dispatch_id"]
    assert dispatch_id is not None

    from eidolon.orchestrator.lib.dispatches import get_dispatch_store

    record = get_dispatch_store().get(dispatch_id)
    assert record is not None
    assert record.engagement_id == eng_id
    assert record.tool_id == "recon.dns.enum"
    assert record.accepted is True
    assert record.tier == "autonomous"


def test_revoked_token_persists_across_db_session(client: TestClient) -> None:
    body = {
        "slug": "rev-eng",
        "purpose": "pentest",
        "scope": {
            "allowed_cidrs": ["10.0.0.0/24"],
            "allowed_actions": ["recon.read"],
            "tier": "autonomous",
        },
    }
    resp = client.post("/v1/engagements/start", json=body).json()
    eng_id = resp["engagement_id"]
    jti = resp["jti"]

    revoke = client.post(
        f"/v1/engagements/{eng_id}/scope-token/revoke",
        json={"jti": jti},
    )
    assert revoke.status_code == 204

    from eidolon.orchestrator.lib.db import reset_db
    from eidolon.orchestrator.lib.revocation import get_revocation_store

    reset_db()
    assert get_revocation_store().is_revoked(jti) is True
