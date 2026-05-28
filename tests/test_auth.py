from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

import eidolon.cli.main as cli_main
from eidolon.orchestrator.app.main import app


def test_health_does_not_require_bearer() -> None:
    unauth = TestClient(app)
    resp = unauth.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_engagement_requires_bearer() -> None:
    unauth = TestClient(app)
    resp = unauth.post("/v1/engagements/start", json={})
    assert resp.status_code == 401
    assert resp.json()["detail"]["reason"] == "missing_authorization"


def test_engagement_rejects_bad_token() -> None:
    bad = TestClient(app, headers={"Authorization": "Bearer not-the-real-token"})
    resp = bad.post("/v1/engagements/start", json={})
    assert resp.status_code == 401
    assert resp.json()["detail"]["reason"] == "bad_token"


def test_orchestrator_init_creates_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli_main.main, ["orchestrator", "init"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["status"] == "created"
    assert "token" in body
    assert (tmp_path / "orchestrator-token").exists()
    mode = (tmp_path / "orchestrator-token").stat().st_mode & 0o777
    assert mode == 0o600


def test_orchestrator_init_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path))
    runner = CliRunner()
    runner.invoke(cli_main.main, ["orchestrator", "init"])
    second = runner.invoke(cli_main.main, ["orchestrator", "init"])
    assert json.loads(second.output)["status"] == "exists"


def test_orchestrator_rotate_replaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path))
    runner = CliRunner()
    first = runner.invoke(cli_main.main, ["orchestrator", "init"])
    t1 = json.loads(first.output)["token"]
    rotated = runner.invoke(cli_main.main, ["orchestrator", "rotate-token"])
    t2 = json.loads(rotated.output)["token"]
    assert t1 != t2


def test_login_writes_laptop_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli_main.main,
        ["login", "--host", "http://example:8000/v1", "--token", "ABC"],
    )
    assert result.exit_code == 0, result.output
    cfg = tmp_path / ".eidolon" / "laptop.json"
    assert cfg.exists()
    data = json.loads(cfg.read_text())
    assert data == {"host": "http://example:8000/v1", "token": "ABC"}
    assert (cfg.stat().st_mode & 0o777) == 0o600


def test_cli_uses_explicit_token_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """--token flag wins over EIDOLON_TOKEN env over local files."""
    captured: dict[str, str | None] = {}

    def factory(base_url: str) -> httpx.Client:
        client = TestClient(app, base_url=base_url)
        original = client.request

        def spy(method, url, **kwargs):
            captured["auth"] = kwargs.get("headers", {}).get("Authorization")
            return original(method, url, **kwargs)

        client.request = spy  # type: ignore[method-assign]
        return client

    monkeypatch.setattr(cli_main, "get_client", factory)
    runner = CliRunner()
    runner.invoke(cli_main.main, ["--token", "FLAG-WINS", "health"])
    assert captured.get("auth") == "Bearer FLAG-WINS"
