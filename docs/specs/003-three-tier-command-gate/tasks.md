# Tasks: Three-tier command gate

Spec: `./spec.md`
Plan: `./plan.md`
Status: In Progress

## Tasks

### T-01 [P] Failing tests for operator registry + signing helpers

File: `tests/test_operator_registry.py`

`test_loads_from_eidolon_home_operators_json`, `test_missing_file_returns_empty_registry`, `test_verify_signature_happy_path`, `test_verify_signature_wrong_key_fails`, `test_verify_signature_tampered_payload_fails`. Must fail before T-05.

### T-02 [P] Failing tests for AuthzStore lifecycle

File: `tests/test_authz_store.py`

`test_create_returns_pending`, `test_approve_marks_approved_records_approver`, `test_approve_after_expiry_raises`, `test_self_approval_raises`, `test_complete_marks_completed`, `test_lookup_unknown_returns_none`. Must fail before T-06.

### T-03 [P] Failing tests for prohibited-tier dispatch flow

File: `tests/test_tool_dispatch_prohibited.py`

`test_prohibited_dispatch_without_authz_returns_202_with_pending_id`, `test_prohibited_dispatch_requires_x_operator_header`, `test_prohibited_dispatch_unknown_operator_returns_404`, `test_dispatch_with_pending_authz_returns_403_authz_not_approved`, `test_dispatch_with_approved_authz_completes`, `test_dispatch_with_expired_authz_returns_403`, `test_dispatch_authz_engagement_mismatch_returns_403`. Must fail before T-07.

### T-04 [P] Failing tests for authorizations router + CLI

Files: `tests/test_authorizations_router.py`, `tests/test_authz_cli.py`

Router: approve happy path, self-approval 409, bad signature 401, expired 410, list per engagement, get by id 404.

CLI: `authz list` prints table, `authz approve --as X --key path` happy path + self-approval rejection + bad-signature exit 1.

### T-05 Implement operators.py

File: `eidolon/orchestrator/lib/operators.py`

`OperatorRecord` Pydantic. `OperatorRegistry` reads `$EIDOLON_HOME/operators.json` lazily, exposes `get(name)`, `verify(name, message_bytes, signature_b64)`. Module-level `get_operator_registry()` singleton with `reset()` for tests.

### T-06 Implement authorization.py

File: `eidolon/orchestrator/lib/authorization.py`

`AuthzStatus`, `PendingAuthorization` Pydantic. `AuthzStore` thread-safe in-memory. Methods: `create(...)`, `get(id)`, `approve(id, approver)`, `complete(id, dispatch_id)`, `list_for_engagement(engagement_id)`, `reset()`. TTL config via `EIDOLON_AUTHZ_TTL_SECONDS` env (default 900). `is_expired(authz, now)` helper.

### T-07 Wire prohibited branch into tools.py

File: `eidolon/orchestrator/app/routers/tools.py`

Read `x-operator` header. Read optional `authz_id` from body. If tier == prohibited: branch to pending creation OR completion. Emit audit events.

### T-08 Add /v1/authorizations router

File: `eidolon/orchestrator/app/routers/authorizations.py`

`POST /{id}/approve`, `GET /{id}`. Wire into `app/main.py` with prefix `/v1/authorizations`. Add `GET /v1/engagements/{id}/authorizations` to engagements router.

### T-09 Add `eidolon authz` CLI group

File: `eidolon/cli/main.py`

`authz list`, `authz approve` commands. Reuse `_request` helper. Sign with PyNaCl `SigningKey(Path(key_path).read_bytes())`.

### T-10 Run make verify, fix anything

## Done when

- [ ] All AC-1..AC-9 tests pass
- [ ] `make verify` passes
- [ ] No constitution rule violations introduced (CON-1, CON-2, CON-7, CON-12)
- [ ] PRD and ROADMAP unchanged (already reflect this scope via § "Three-tier command gate w/ operator co-sign")
