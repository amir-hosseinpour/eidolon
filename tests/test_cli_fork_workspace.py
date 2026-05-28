from __future__ import annotations

import json
from pathlib import Path

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


def _start(runner: CliRunner, slug: str) -> dict:
    result = runner.invoke(
        cli_main.main,
        ["engage", "start", "--slug", slug, "--purpose", "ctf"],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_fork_open_list_resolve_via_cli(runner: CliRunner) -> None:
    eng = _start(runner, slug="cli-fork")
    eid = eng["engagement_id"]

    opened = runner.invoke(
        cli_main.main,
        [
            "fork",
            "open",
            eid,
            "--type",
            "noise_threshold",
            "--prompt",
            "scan 200 hosts?",
            "--context",
            json.dumps({"hosts": 200}),
        ],
    )
    assert opened.exit_code == 0, opened.output
    fork_body = json.loads(opened.output)
    fork_id = fork_body["fork"]["id"]

    listed = runner.invoke(
        cli_main.main, ["fork", "list", eid, "--status", "open"]
    )
    assert listed.exit_code == 0, listed.output
    assert fork_id in listed.output

    show = runner.invoke(cli_main.main, ["fork", "show", eid, fork_id])
    assert show.exit_code == 0, show.output
    assert json.loads(show.output)["id"] == fork_id

    resolved = runner.invoke(
        cli_main.main,
        [
            "fork",
            "resolve",
            fork_id,
            "--resolution",
            "approved",
            "--operator",
            "damion",
            "--rationale",
            "approved scope",
        ],
    )
    assert resolved.exit_code == 0, resolved.output
    body = json.loads(resolved.output)
    assert body["fork"]["status"] == "approved"


def test_fork_show_returns_error_for_missing_fork(runner: CliRunner) -> None:
    eng = _start(runner, slug="cli-fork-missing")
    eid = eng["engagement_id"]
    res = runner.invoke(cli_main.main, ["fork", "show", eid, "FORK-nope"])
    assert res.exit_code == 1
    assert json.loads(res.output)["error"] == "not_found"


def test_workspace_edit_inline_note(
    tmp_path: Path, runner: CliRunner
) -> None:
    from eidolon.orchestrator.lib.engagements import EngagementStore
    from eidolon.orchestrator.lib.scope import ScopeDocument
    from eidolon.orchestrator.lib.templates import load_template_by_name
    from eidolon.orchestrator.lib.workspace import EngagementWorkspace

    engagement = EngagementStore().create(
        slug="cli-ws",
        purpose="pentest",
        scope=ScopeDocument(
            allowed_cidrs=["10.42.0.0/24"],
            allowed_actions=["recon.read"],
            tier="confirm",
        ),
    )
    EngagementWorkspace(engagement.id).init_from_template(
        load_template_by_name("blank-kali"), engagement.scope
    )

    res = runner.invoke(
        cli_main.main,
        [
            "engage",
            "workspace-edit",
            engagement.id,
            "--note",
            "first observation from cli",
        ],
    )
    assert res.exit_code == 0, res.output
    body = json.loads(res.output)
    assert body["status"] == "ok"
    assert "first observation from cli" in Path(body["path"]).read_text()


def test_workspace_edit_rejects_empty_note(
    tmp_path: Path, runner: CliRunner
) -> None:
    res = runner.invoke(
        cli_main.main,
        ["engage", "workspace-edit", "ENG-fake", "--note", "   "],
    )
    assert res.exit_code == 1
    assert json.loads(res.output)["error"] == "empty_note"
