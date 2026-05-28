import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "EIDOLON_HMAC_SECRET",
    "test-secret-not-for-prod-minimum-32-bytes!!",
)


@pytest.fixture(autouse=True)
def _isolated_eidolon_home(tmp_path, monkeypatch):
    """Pin EIDOLON_HOME to a tmp dir so tests never write to the real ~/.eidolon."""
    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path / "eidolon-home"))
    from eidolon.orchestrator.lib.audit import reset_audit_chain
    from eidolon.orchestrator.lib.db import reset_db

    reset_db()
    reset_audit_chain()
    yield
    reset_db()
    reset_audit_chain()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    from eidolon.orchestrator.lib.auth import load_or_create_token

    return {"Authorization": f"Bearer {load_or_create_token()}"}


@pytest.fixture
def client(auth_headers: dict[str, str]) -> TestClient:
    from eidolon.orchestrator.app.main import app

    return TestClient(app, headers=auth_headers)
