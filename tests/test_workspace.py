from __future__ import annotations

import json
from pathlib import Path

import pytest

from eidolon.orchestrator.lib.scope import ScopeDocument
from eidolon.orchestrator.lib.templates import load_template_by_name
from eidolon.orchestrator.lib.workspace import (
    EngagementWorkspace,
    WorkspaceError,
    workspace_root,
)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _scope() -> ScopeDocument:
    return ScopeDocument(
        allowed_cidrs=["10.42.0.0/24"],
        allowed_actions=["recon.read", "recon.active"],
        tier="confirm",
        rules_of_engagement="No DoS. No data exfil. Daylight hours only.",
    )


def test_init_from_blank_kali_template_creates_workspace() -> None:
    loaded = load_template_by_name("blank-kali")
    ws = EngagementWorkspace("ENG-TEST-1")

    ws.init_from_template(loaded, _scope())

    assert ws.exists()
    assert ws.scope_path.is_file()
    assert ws.manifest_path.is_file()
    assert ws.notes_dir.is_dir()
    assert ws.decisions_dir.is_dir()
    assert ws.findings_dir.is_dir()

    manifest = json.loads(ws.manifest_path.read_text())
    assert manifest["template"]["name"] == "blank-kali"
    assert manifest["scope_summary"]["tier"] == "confirm"
    assert "10.42.0.0/24" in manifest["scope_summary"]["allowed_cidrs"]


def test_init_is_not_idempotent_on_existing_root() -> None:
    loaded = load_template_by_name("blank-kali")
    ws = EngagementWorkspace("ENG-TEST-2")
    ws.init_from_template(loaded, _scope())
    with pytest.raises(WorkspaceError):
        ws.init_from_template(loaded, _scope())


def test_write_note_appends_with_timestamp_header() -> None:
    loaded = load_template_by_name("blank-kali")
    ws = EngagementWorkspace("ENG-TEST-3")
    ws.init_from_template(loaded, _scope())

    p1 = ws.write_note("Discovered open SSH on host A.", date="2026-04-26")
    p2 = ws.write_note("Confirmed credential reuse.", date="2026-04-26")

    assert p1 == p2
    body = p1.read_text()
    assert body.startswith("# Notes - 2026-04-26")
    assert body.count("## ") == 2  # one per appended chunk
    assert "Discovered open SSH" in body
    assert "Confirmed credential reuse" in body


def test_write_note_rejects_empty_body() -> None:
    loaded = load_template_by_name("blank-kali")
    ws = EngagementWorkspace("ENG-TEST-4")
    ws.init_from_template(loaded, _scope())
    with pytest.raises(WorkspaceError):
        ws.write_note("   ")


def test_write_decision_creates_decision_file() -> None:
    loaded = load_template_by_name("blank-kali")
    ws = EngagementWorkspace("ENG-TEST-5")
    ws.init_from_template(loaded, _scope())

    path = ws.write_decision(
        "fork-001",
        prompt="Operator approval to add 192.168.5.0/24 to scope?",
        resolution="approved",
        operator="damion",
        rationale="Client confirmed via Signal at 14:02 EST.",
    )
    assert path.is_file()
    body = path.read_text()
    assert "# Decision: fork-001" in body
    assert "approved" in body
    assert "damion" in body


def test_write_finding_uses_slug_filename() -> None:
    loaded = load_template_by_name("blank-kali")
    ws = EngagementWorkspace("ENG-TEST-6")
    ws.init_from_template(loaded, _scope())

    path = ws.write_finding(
        "Stored XSS in admin notes",
        severity="high",
        body="Reflected payload renders in /admin/notes",
        cwe="CWE-79",
    )
    assert path.name == "stored-xss-in-admin-notes.md"
    body = path.read_text()
    assert "# Stored XSS in admin notes" in body
    assert "CWE-79" in body


def test_log_records_lifecycle_events_in_order() -> None:
    loaded = load_template_by_name("blank-kali")
    ws = EngagementWorkspace("ENG-TEST-7")
    ws.init_from_template(loaded, _scope())
    ws.write_note("note body", date="2026-04-26")
    ws.write_decision(
        "fork-x", prompt="?", resolution="approved", operator="op", rationale=""
    )
    ws.write_finding("x", severity="low", body="b")

    events = ws.read_log()
    kinds = [e["kind"] for e in events]
    assert kinds == [
        "workspace_init",
        "note_appended",
        "decision_written",
        "finding_written",
    ]


def test_erase_removes_workspace_dir() -> None:
    loaded = load_template_by_name("blank-kali")
    ws = EngagementWorkspace("ENG-TEST-8")
    ws.init_from_template(loaded, _scope())
    assert ws.exists()
    ws.erase()
    assert not ws.exists()


def test_workspace_root_under_eidolon_home(tmp_path: Path) -> None:
    root = workspace_root("ENG-LOC")
    assert root.parent.name == "ENG-LOC"
    assert root.name == "workspace"
