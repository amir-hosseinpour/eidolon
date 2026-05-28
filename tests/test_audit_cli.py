from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from click.testing import CliRunner

import eidolon.cli.main as cli_main
from eidolon.orchestrator.lib.audit import AuditChain, reset_audit_chain


@pytest.fixture(autouse=True)
def _reset_chain():
    reset_audit_chain()
    yield
    reset_audit_chain()


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_audit_head_prints_head_and_seq(runner: CliRunner) -> None:
    chain = AuditChain()
    e1 = chain.append("engagement_start", engagement_id="ENG-1")

    result = runner.invoke(cli_main.main, ["audit", "head"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["head"] == e1.hash
    assert body["seq"] == 1
    today = datetime.now(UTC).date().isoformat()
    assert today in body["segment"]


def test_audit_verify_clean_segment(runner: CliRunner) -> None:
    chain = AuditChain()
    for i in range(3):
        chain.append("scope_audit", engagement_id="ENG-1", reason=f"r{i}")

    result = runner.invoke(cli_main.main, ["audit", "verify"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["ok"] is True
    assert body["broken_seq"] is None


def test_audit_verify_tampered_segment_exit_1_and_seq(runner: CliRunner) -> None:
    chain = AuditChain()
    for i in range(5):
        chain.append("scope_audit", engagement_id="ENG-1", reason=f"r{i}")

    today = datetime.now(UTC).date()
    seg = chain.segment_path_for(today)
    lines = seg.read_text().splitlines()
    third = json.loads(lines[2])
    third["reason"] = "tampered"
    lines[2] = json.dumps(third, sort_keys=True, separators=(",", ":"))
    seg.write_text("\n".join(lines) + "\n")

    result = runner.invoke(
        cli_main.main, ["audit", "verify", "--segment", today.isoformat()]
    )
    assert result.exit_code == 1
    body = json.loads(result.output)
    assert body["ok"] is False
    assert body["broken_seq"] == 3
