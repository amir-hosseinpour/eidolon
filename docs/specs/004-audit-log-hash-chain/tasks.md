# Tasks: Audit log hash chain

Spec: `./spec.md`
Plan: `./plan.md`
Status: In Progress

## Tasks

### T-01 [P] Failing tests for AuditEntry + AuditChain core

File: `tests/test_audit_chain.py`

`test_first_append_uses_zero_prev_hash`, `test_seq_increments_monotonically`, `test_head_returns_last_hash`, `test_verify_segment_happy_path`, `test_tamper_byte_breaks_verify_returns_seq`, `test_multi_segment_continuity` (monkeypatch UTC date), `test_audit_dir_mode_0700`. Must fail before T-04.

### T-02 [P] Failing tests for `eidolon audit head|verify`

File: `tests/test_audit_cli.py`

`test_audit_head_prints_head_and_seq`, `test_audit_verify_clean_segment`, `test_audit_verify_tampered_segment_exit_1_and_seq`. Must fail before T-08.

### T-03 [P] Failing test for cert anchoring

File: `tests/test_engagement_erase.py` (extend)

`test_cert_anchors_to_real_audit_head`: open engagement, append a few events, close+erase, assert `audit_head_at_open != "0"*64`, assert `audit_head_at_close` matches `AuditChain.head()` after erase.

### T-04 Implement audit.py

File: `eidolon/orchestrator/lib/audit.py`

- `AuditEntry` Pydantic with all fields from spec.
- `_compute_hash(prev_hash, payload_dict) -> str` (sha256, canonical JSON).
- `AuditChain` class:
  - `__init__()` reads existing segments, recovers seq + head.
  - `append(event_name, **fields) -> AuditEntry` — atomic append, returns entry.
  - `head() -> str`.
  - `current_seq() -> int`.
  - `segment_path_for(date) -> Path`.
  - `verify(path) -> tuple[bool, int | None]`.
  - `reset()` for tests.
- Module-level `get_audit_chain()` singleton + `reset_audit_chain()` for tests.
- Module-level `emit_audit(event_name, **fields)` convenience.

### T-05 Delete audit_stub.py + update all callers

Files: `eidolon/orchestrator/lib/audit_stub.py` (delete), `engagements.py`, `tools.py`, `authorizations.py` (update imports).

Replace `emit_scope_audit({"event": X, "k": v, ...})` with `emit_audit(X, k=v, ...)`. Discard fields the AuditEntry doesn't model (or extend AuditEntry — the spec lists the standard set; keep audit logging strict).

### T-06 Wire audit_head_at_open into Engagement

Files: `eidolon/orchestrator/lib/engagements.py`, `eidolon/orchestrator/app/routers/engagements.py`.

- Add `audit_head_at_open: str = STUB_HEAD` field.
- `engagement_start` endpoint: capture `head_before = AuditChain.head()` BEFORE emitting `engagement_start` event, pass to `store.create(..., audit_head_at_open=head_before)`.

### T-07 Wire cert close-head anchoring

File: `eidolon/orchestrator/app/routers/engagements.py`.

`engagement_erase`: emit `engagement_erased` event, then read `head_after = AuditChain.head()` (which now includes the erased event). Build cert with `audit_head_at_open = engagement.audit_head_at_open`, `audit_head_at_close = head_after`. Sign + return.

### T-08 Add CLI audit subgroup

File: `eidolon/cli/main.py`.

```
eidolon audit head
eidolon audit verify [--segment YYYY-MM-DD]
```

`head` returns local chain head (no orchestrator round-trip — read directly from disk via `AuditChain`). Same for `verify`. Print JSON. `verify` exits 1 on broken chain.

### T-09 Run make verify, fix anything

## Done when

- [ ] All AC-1..AC-9 tests pass
- [ ] `make verify` passes
- [ ] No constitution rule violations (CON-3, CON-9, CON-12 added; previous rules still hold)
- [ ] `audit_stub.py` removed; no `emit_scope_audit` references remain
- [ ] Cert of Destruction `audit_head_at_open` + `audit_head_at_close` are real chain hashes
