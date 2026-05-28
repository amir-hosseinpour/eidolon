from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from eidolon.orchestrator.lib import audit as audit_mod
from eidolon.orchestrator.lib.audit import (
    AuditChain,
    AuditEntry,
    reset_audit_chain,
)


@pytest.fixture(autouse=True)
def _reset_chain():
    reset_audit_chain()
    yield
    reset_audit_chain()


def _audit_root() -> Path:
    return Path(os.environ["EIDOLON_HOME"]) / "audit"


def test_first_append_uses_zero_prev_hash() -> None:
    chain = AuditChain()
    entry = chain.append("engagement_start", engagement_id="ENG-1")
    assert isinstance(entry, AuditEntry)
    assert entry.seq == 1
    assert entry.prev_hash == "0" * 64
    assert entry.event == "engagement_start"
    assert entry.engagement_id == "ENG-1"
    expected_payload = entry.model_dump(exclude={"hash"})
    body = json.dumps(expected_payload, sort_keys=True, separators=(",", ":")).encode()
    assert entry.hash == hashlib.sha256(("0" * 64).encode() + body).hexdigest()


def test_seq_increments_monotonically() -> None:
    chain = AuditChain()
    e1 = chain.append("engagement_start", engagement_id="ENG-1")
    e2 = chain.append("scope_token_issued", engagement_id="ENG-1", jti="JTI-1")
    e3 = chain.append("tool_dispatch_accepted", engagement_id="ENG-1", tool_id="recon")
    assert (e1.seq, e2.seq, e3.seq) == (1, 2, 3)
    assert e2.prev_hash == e1.hash
    assert e3.prev_hash == e2.hash


def test_head_returns_last_hash() -> None:
    chain = AuditChain()
    assert chain.head() == "0" * 64
    e1 = chain.append("engagement_start", engagement_id="ENG-1")
    assert chain.head() == e1.hash
    e2 = chain.append("engagement_close", engagement_id="ENG-1")
    assert chain.head() == e2.hash
    assert chain.current_seq() == 2


def test_verify_segment_happy_path() -> None:
    chain = AuditChain()
    for i in range(5):
        chain.append("scope_audit", engagement_id="ENG-1", seq_marker=str(i))
    today = datetime.now(UTC).date()
    seg = chain.segment_path_for(today)
    ok, broken = chain.verify(seg)
    assert ok is True
    assert broken is None


def test_tamper_byte_breaks_verify_returns_seq() -> None:
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
    ok, broken = chain.verify(seg)
    assert ok is False
    assert broken == 3


def test_multi_segment_continuity(monkeypatch: pytest.MonkeyPatch) -> None:
    chain = AuditChain()

    fake_today = date(2026, 4, 26)

    def _fake_today() -> date:
        return fake_today

    monkeypatch.setattr(audit_mod, "_utc_today", _fake_today)
    e1 = chain.append("engagement_start", engagement_id="ENG-1")
    e2 = chain.append("scope_audit", engagement_id="ENG-1")

    fake_today = date(2026, 4, 27)
    e3 = chain.append("engagement_close", engagement_id="ENG-1")

    assert e3.prev_hash == e2.hash
    assert e3.seq == 3
    seg_old = chain.segment_path_for(date(2026, 4, 26))
    seg_new = chain.segment_path_for(date(2026, 4, 27))
    assert seg_old.exists()
    assert seg_new.exists()
    assert seg_old != seg_new
    assert e1.hash != e3.hash


def test_audit_dir_mode_0700() -> None:
    chain = AuditChain()
    chain.append("engagement_start", engagement_id="ENG-1")
    root = _audit_root()
    assert root.exists()
    mode = root.stat().st_mode & 0o777
    assert mode == 0o700
