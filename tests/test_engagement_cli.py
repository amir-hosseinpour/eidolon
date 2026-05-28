from __future__ import annotations

import json
from pathlib import Path

import click
import httpx
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

import eidolon.cli.main as cli_main
from eidolon.orchestrator.app.main import app


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    def _factory(base_url: str) -> httpx.Client:
        return TestClient(app, base_url=base_url)

    monkeypatch.setattr(cli_main, "get_client", _factory)
    return CliRunner()


def _open(runner: CliRunner, slug: str = "cli-test", roe_path: str | None = None) -> dict:
    args = ["engage", "start", "--slug", slug, "--purpose", "ctf"]
    if roe_path:
        args.extend(["--rules-of-engagement", roe_path])
    result = runner.invoke(cli_main.main, args)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_engagement_open_prints_id(tmp_path: Path, runner: CliRunner) -> None:
    roe = tmp_path / "roe.md"
    roe.write_text("be nice")
    body = _open(runner, slug="open-test", roe_path=str(roe))
    assert body["engagement_id"].startswith("ENG-")
    assert body["status"] == "active"
    assert body["scope_token"]
    assert body["jti"]


def test_engagement_scope_mints_token(runner: CliRunner) -> None:
    eng = _open(runner, slug="scope-test")
    eid = eng["engagement_id"]

    result = runner.invoke(
        cli_main.main,
        [
            "engage",
            "scope",
            eid,
            "--target",
            "10.0.0.0/24",
            "--permit",
            "recon.read",
            "--tier",
            "autonomous",
            "--ttl",
            "30m",
        ],
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["engagement_id"] == eid
    assert body["token"]
    assert body["jti"]


def test_engagement_close_then_scope_returns_error(runner: CliRunner) -> None:
    eng = _open(runner, slug="close-test")
    eid = eng["engagement_id"]

    closed = runner.invoke(cli_main.main, ["engage", "close", eid])
    assert closed.exit_code == 0
    assert json.loads(closed.output)["engagement"]["status"] == "closed"

    again = runner.invoke(
        cli_main.main,
        [
            "engage",
            "scope",
            eid,
            "--target",
            "10.0.0.0/24",
            "--permit",
            "recon.read",
            "--tier",
            "autonomous",
            "--ttl",
            "1h",
        ],
    )
    assert again.exit_code == 1
    assert "409" in again.output


def test_engagement_erase_returns_erased_state(runner: CliRunner) -> None:
    eng = _open(runner, slug="erase-cli")
    eid = eng["engagement_id"]

    result = runner.invoke(cli_main.main, ["engage", "erase", eid])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["engagement"]["id"] == eid
    assert body["engagement"]["status"] == "erased"
    assert body["engagement"]["audit_head_at_close"] is not None


def test_engagement_show_returns_state(runner: CliRunner) -> None:
    eng = _open(runner, slug="show-test")
    eid = eng["engagement_id"]

    result = runner.invoke(
        cli_main.main,
        ["engage", "show", eid, "--with-tokens", "--with-audit-head"],
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["engagement"]["id"] == eid
    assert "issued_tokens" in body
    assert body["audit_head"]["head"] != "0" * 64
    assert len(body["audit_head"]["head"]) == 64


def test_engagement_list_prints_table(runner: CliRunner) -> None:
    _open(runner, slug="list-a")
    _open(runner, slug="list-b")

    result = runner.invoke(cli_main.main, ["engage", "list"])
    assert result.exit_code == 0, result.output
    assert "list-a" in result.output
    assert "list-b" in result.output


def test_parse_ttl_accepts_known_suffixes() -> None:
    assert cli_main.parse_ttl("8h") == 28800
    assert cli_main.parse_ttl("30m") == 1800
    assert cli_main.parse_ttl("3600s") == 3600


def test_parse_ttl_rejects_unknown_suffix() -> None:
    with pytest.raises(click.BadParameter):
        cli_main.parse_ttl("3d")
