# Plan: Three-tier command gate

Spec: `./spec.md`
Status: Approved
Updated: 2026-04-26

## Architecture

Three new modules + extensions to two existing routers:

```
eidolon/orchestrator/lib/operators.py       (new)  -> OperatorRegistry, sign helpers
eidolon/orchestrator/lib/authorization.py   (new)  -> AuthzStore + PendingAuthorization model
eidolon/orchestrator/app/routers/authorizations.py (new) -> /v1/authorizations endpoints
eidolon/orchestrator/app/routers/tools.py   (modify) -> prohibited-tier branching
eidolon/orchestrator/app/routers/engagements.py (modify) -> /v1/engagements/{id}/authorizations
eidolon/cli/main.py                          (modify) -> `eidolon authz {list,approve}`
```

## Data model

```python
class OperatorRecord(BaseModel):
    name: str
    pubkey: str  # base64-encoded Ed25519 public key

class AuthzStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"
    completed = "completed"

class PendingAuthorization(BaseModel):
    id: str                    # AUTHZ-<ts>-<hex>
    engagement_id: str
    tool_id: str
    target: str | None
    action: ScopeAction
    requested_by: str          # operator name from x-operator header
    requested_at: int
    expires_at: int            # requested_at + EIDOLON_AUTHZ_TTL_SECONDS (default 900)
    status: AuthzStatus = AuthzStatus.pending
    approver: str | None = None
    approved_at: int | None = None
    completed_at: int | None = None
    dispatch_id: str | None = None
```

## Endpoint contracts

### `POST /v1/tools/dispatch` — prohibited branch

Request body adds optional `authz_id: str | None = None`. Also reads `x-operator` header (required when tier resolves to prohibited).

Behavior:
1. Verify scope token (Spec 001 path, unchanged for autonomous + confirm).
2. If tier == prohibited:
   - If `authz_id` is None:
     - Read `x-operator` header. 400 if missing. 404 if operator not in registry.
     - Create `PendingAuthorization`, emit `tool_dispatch_pending`, return 202 with `{pending_authorization_id, expires_at, requires: "operator_cosign"}`.
   - Else:
     - Lookup authz. 404 if missing.
     - 403 `authz_expired` if past `expires_at`.
     - 403 `authz_not_approved` if status != approved.
     - 403 `authz_engagement_mismatch` if engagement differs.
     - Mark completed, emit `tool_dispatch_completed`, return ToolDispatchResponse.

### `POST /v1/authorizations/{id}/approve`

Request body: `{operator: str, signature: str (b64)}`.

Behavior:
1. Lookup authz. 404 if missing. 410 if expired or already completed.
2. 409 `self_approval_forbidden` if `operator == requested_by`.
3. Lookup operator pubkey. 404 if not in registry.
4. Verify Ed25519 signature against canonical JSON `{"authz_id": <id>, "decision": "approve"}` (sort_keys, separators=(",", ":")).
5. 401 `bad_signature` if verify fails.
6. Mark approved, emit `authz_approved` event, return updated authz.

### `GET /v1/authorizations/{id}` — single record.

### `GET /v1/engagements/{id}/authorizations` — list per engagement.

## CLI surface

```
eidolon authz list <engagement_id>
eidolon authz approve <authz_id> --as <operator> --key <path>
```

`approve` reads the Ed25519 private key bytes from `--key`, signs the canonical payload, posts. Prints the updated record JSON or the error reason and exits 1.

`list` prints a Rich table: id, status, requested_by, approver, expires_at.

## Test strategy (TDD)

Three test files, all written failing before implementation:

1. `tests/test_authorizations.py` — model + store + signature verification.
2. `tests/test_tool_dispatch_prohibited.py` — 202-pending then approve then complete; expired; bad authz_id; engagement mismatch.
3. `tests/test_authz_cli.py` — `eidolon authz approve` happy path + self-approval rejection + bad signature.

Use the existing `EIDOLON_HOME` autouse fixture; write `operators.json` per-test with deterministic keys generated on the fly.

## Sequencing

Pre: AC text frozen above. Tests landed before implementation.

1. Failing tests for `OperatorRegistry` + signature roundtrip.
2. Failing tests for `AuthzStore` lifecycle (create, approve, expire, complete).
3. Failing tests for `/v1/tools/dispatch` prohibited branch.
4. Failing tests for `/v1/authorizations/*`.
5. Failing tests for CLI.
6. Implement `operators.py` + `authorization.py` + `authorizations.py` router + tools.py extension + CLI commands.
7. Run `make verify`. Iterate.

## Risks + mitigations

- **Risk:** Header-based requester identity is spoofable. **Mitigation:** Spec 006 ticket queued in ROADMAP, doc'd in spec § Out of scope. Approver still needs the private key, so the worst-case (spoofed requester) doesn't bypass co-sign.
- **Risk:** AuthzStore is process-local; restart loses pending authorizations. **Mitigation:** Acceptable for v0.1 (DefCon demo restarts pre-recorded). v0.2 SQLite migration covers it.
- **Risk:** Test flake on `expires_at` boundary. **Mitigation:** Use `monkeypatch` on `time.time()` in tests, never rely on real clock.

## Constitution gate plan

- CON-1 — primitives stay control-plane.
- CON-2 — per-call authz now enforced for prohibited tier.
- CON-7 — co-sign rule lands here.
- CON-12 — gates section in spec.

## Done criteria

- [ ] All AC-1..AC-9 tests pass.
- [ ] `make verify` clean.
- [ ] No mypy warnings, no ruff violations.
- [ ] CLI smoke: open engagement, attempt prohibited tool, approve from a second operator, complete.
