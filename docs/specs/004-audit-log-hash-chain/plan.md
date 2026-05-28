# Plan: Audit log hash chain

Spec: `./spec.md`
Status: Approved
Updated: 2026-04-26

## Architecture

```
eidolon/orchestrator/lib/audit.py        (new)    -> AuditEntry, AuditChain, emit_audit
eidolon/orchestrator/lib/audit_stub.py   (delete) -> replaced by audit.py
eidolon/orchestrator/lib/engagements.py  (modify) -> Engagement.audit_head_at_open
eidolon/orchestrator/app/routers/engagements.py (modify) -> erase reads heads, signs into cert
eidolon/orchestrator/app/routers/tools.py        (modify) -> import emit_audit
eidolon/orchestrator/app/routers/authorizations.py (modify) -> import emit_audit
eidolon/cli/main.py                       (modify) -> `eidolon audit head|verify`
```

## Data model

```python
class AuditEntry(BaseModel):
    seq: int
    ts: int
    event: str
    engagement_id: str | None = None
    operator_id: str | None = None
    action: str | None = None
    target: str | None = None
    tier: str | None = None
    dispatch_id: str | None = None
    authz_id: str | None = None
    jti: str | None = None
    reason: str | None = None
    prev_hash: str
    hash: str

    @classmethod
    def compute_hash(cls, *, prev_hash: str, payload: dict) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(prev_hash.encode() + body).hexdigest()
```

Hash payload = `entry.model_dump(exclude={"hash"})`.

## Storage layout

```
$EIDOLON_HOME/
  audit/                              (mode 0700)
    audit-2026-04-26.jsonl            (UTC date, one entry per line, O_APPEND)
    audit-2026-04-27.jsonl
    state.json                        (cached current_seq + current_head, refreshed on append)
```

`state.json` is a convenience cache; the source of truth is the JSONL files. On startup or first append, the chain reads the latest segment to recover seq and head.

## Append flow

1. Acquire process-local lock.
2. Determine UTC date → segment filename.
3. If segment file does not exist:
   - If a previous segment exists, read its tail hash → that becomes this entry's `prev_hash`.
   - Else `prev_hash = "0"*64`.
   - Update seq from prior segment's tail seq + 1, or start at 1.
4. Build payload (seq, ts, event, optional fields), compute hash, build full entry.
5. Open segment with `os.open(..., O_WRONLY|O_APPEND|O_CREAT, 0o600)`.
6. Write `json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"`.
7. Update in-memory `(current_head, current_seq)`.
8. Release lock.

## Verification flow

```python
def verify(path) -> tuple[bool, int | None]:
    prev_hash = "0" * 64  # or seg-bootstrap from preceding segment
    expected_seq = 1       # or last seq of preceding segment + 1
    for line in path.read_text().splitlines():
        entry = json.loads(line)
        if entry["seq"] != expected_seq:
            return False, entry["seq"]
        if entry["prev_hash"] != prev_hash:
            return False, entry["seq"]
        recomputed = compute_hash(prev_hash=entry["prev_hash"],
                                  payload={k: v for k, v in entry.items() if k != "hash"})
        if recomputed != entry["hash"]:
            return False, entry["seq"]
        prev_hash = entry["hash"]
        expected_seq += 1
    return True, None
```

For v0.1 a segment is verified standalone using its own bootstrap (ignoring cross-segment seq continuity). v0.2 will pass the prior segment's tail to enable cross-segment verification.

## Cert of Destruction wiring

- `Engagement` model gains `audit_head_at_open: str` (default `STUB_HEAD`, populated at engagement_start).
- `engagement_start` reads `AuditChain.head()` BEFORE emitting the `engagement_start` event, stamps it on the engagement record. (Order matters: head-at-open is the head *just before* this engagement's first audit entry.)
- Erase endpoint reads current head, sets `cert.audit_head_at_open = engagement.audit_head_at_open` and `cert.audit_head_at_close = AuditChain.head()` (head AFTER the engagement_erased event is appended? — see decision below).

Decision: cert's `audit_head_at_close` = head AFTER the engagement_erased event is appended. This means the cert's signature commits to a chain state that includes the destruction event itself. Customers can independently re-walk the chain and recompute the head, then verify the signature.

## Test strategy (TDD)

Three test files:
1. `tests/test_audit_chain.py` — append, head, verify happy path, verify tamper, multi-segment continuity (mock UTC date).
2. `tests/test_audit_cli.py` — `eidolon audit head`, `eidolon audit verify` happy + tampered (writes a synthetic broken file).
3. `tests/test_cert_of_destruction.py` — extend with: `test_cert_anchors_to_real_audit_head` asserting `audit_head_at_open != STUB_HEAD` and `audit_head_at_close` is the chain head.

Plus update existing tests to expect file-based audit (the autouse `EIDOLON_HOME` fixture already isolates).

## Sequencing

1. Failing tests for `AuditEntry` + `AuditChain.append`/`head`/`verify`.
2. Failing test for tamper detection.
3. Failing tests for CLI `audit head` + `audit verify`.
4. Failing test for cert head anchoring.
5. Implement `audit.py`.
6. Replace `audit_stub` callers with `emit_audit`.
7. Wire `audit_head_at_open` into engagement model + start endpoint.
8. Wire cert close-head anchoring.
9. Add CLI `audit head` + `audit verify`.
10. Run `make verify`.

## Risks + mitigations

- **Risk:** Tests collide with each other if they share `$EIDOLON_HOME`. **Mitigation:** the autouse fixture already pins per-test tmp dir.
- **Risk:** Process-restart loses in-memory seq counter. **Mitigation:** read on first call; `state.json` cache for hot path.
- **Risk:** Hash recomputation is expensive on big segments during verify. **Mitigation:** v0.1 demo segments are small; v0.2 ticket for mmap + parallel verify.

## Constitution gate plan

- CON-3 lands here.
- CON-9 cert anchoring lands here.

## Done criteria

- [ ] AC-1..AC-9 tests pass.
- [ ] `make verify` clean.
- [ ] `audit_stub.py` deleted, no callers remain.
- [ ] Cert of Destruction includes non-zero `audit_head_at_open` and `audit_head_at_close`.
