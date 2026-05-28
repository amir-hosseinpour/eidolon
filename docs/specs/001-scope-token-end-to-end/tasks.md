# Tasks: Scope token end to end

Spec: `./spec.md`
Plan: `./plan.md`
Status: In Progress
Updated: 2026-04-26

## Conventions

- Tasks are executable units, scoped to a single PR ideally.
- `[P]` marks tasks that can be done in parallel with the previous task.
- Each task names exact files to touch and what to assert.
- Tests come BEFORE implementation. Failing test then make it pass.

## Tasks

### T-01 Write failing tests for AC-1 issuance and AC-3 revocation

File: `tests/test_scope_token.py`

Add `test_issue_scope_token_returns_token_jti_engagement_id_exp` and `test_revoke_then_verify_returns_401_token_revoked`. Hits `/v1/engagements/{id}/scope-token` and `/v1/engagements/{id}/scope-token/revoke`. They must fail before T-04.

### T-02 [P] Write failing tests for AC-2 verification failure modes

File: `tests/test_scope_token.py`

Parametrized `test_verify_rejects` with one row per failure reason: `token_invalid`, `token_expired`, `token_revoked`, `engagement_mismatch`, `target_out_of_scope`, `action_out_of_scope`, `tier_exceeded`. Each asserts `(status_code, reason)`.

### T-03 [P] Write failing tests for AC-4 CIDR boundary and AC-5 tier ordering

File: `tests/test_scope_token.py`

`test_cidr_boundary_rejects_one_bit_outside`, `test_tier_ordering_autonomous_confirm_prohibited`. Each AC-5 row checks that token tier T1 admits tool tier T2 ≤ T1 and rejects T2 > T1.

### T-04 Extend ScopeDocument with tier field

Files: `eidolon/orchestrator/lib/scope.py`

Add `ScopeTier = Literal["autonomous", "confirm", "prohibited"]`, add `tier: ScopeTier` to `ScopeDocument`. Existing tests (`test_smoke.py`) updated to pass the new field.

### T-05 Rename Session → Engagement

Files: `eidolon/orchestrator/lib/sessions.py` → `engagements.py`; `eidolon/orchestrator/app/routers/sessions.py` → `engagements.py`; `eidolon/orchestrator/app/main.py` (router include); `tests/test_smoke.py` (paths).

Class `Session` → `Engagement`, `SessionStatus` → `EngagementStatus`, `SessionStore` → `EngagementStore`. Routes `/v1/sessions/...` → `/v1/engagements/...`. JWT `sub` semantically carries engagement ID (no rename of claim itself).

### T-06 Add revocation store

File: `eidolon/orchestrator/lib/revocation.py` (new)

`RevocationStore` with thread-safe set of revoked JTIs. Singleton `get_revocation_store()`. Methods `revoke(jti)`, `is_revoked(jti)`. Comment notes process-local v0.1 limitation.

### T-07 Add typed verification with ScopeError

Files: `eidolon/orchestrator/lib/scope.py`

`ScopeError` exception with `status_code`, `reason`. `VerifiedToken` dataclass. `verify_scope_token(token, expected_engagement, target=None, action=None, requested_tier=None)` runs the seven checks in order; each failure raises `ScopeError(status_code, reason)`.

### T-08 Add FastAPI dependency

File: `eidolon/orchestrator/app/dependencies.py` (new)

`require_scope_token(engagement_id, x_scope_token)` dependency that calls `verify_scope_token` and raises `HTTPException(status_code, detail={"reason": ...})` on `ScopeError`. Returns `VerifiedToken`.

### T-09 Implement engagements router with scope-token endpoints

Files: `eidolon/orchestrator/app/routers/engagements.py`

`POST /v1/engagements/{engagement_id}/scope-token` issues a token; rejects 404 if engagement missing, 409 if closed. `POST /v1/engagements/{engagement_id}/scope-token/revoke` 204s and updates revocation store.

### T-10 Update tools router to use dependency and tier check

Files: `eidolon/orchestrator/app/routers/tools.py`

`tool_dispatch` now takes `verified: VerifiedToken = Depends(require_scope_token)`. Tier check: tool tier must be ≤ `verified.scope.tier`. Confirm tier still requires `confirm_token` (unchanged).

### T-11 Stub audit hook

File: `eidolon/orchestrator/lib/audit_stub.py` (new)

`emit_scope_audit(event: dict)` writes one structlog line. `verify_scope_token` calls it on success and on each typed failure.

### T-12 Run make verify, fix anything

`make verify` must pass. Update `mypy` if a Literal narrowing tickle. Update existing `test_smoke.py` to satisfy the rename.

## Done when

- [ ] All AC-1..AC-5 tests pass
- [ ] `make verify` passes
- [ ] No constitution rule violations introduced (CON-4, CON-5, CON-7, CON-12)
- [ ] No `Session*` symbols remain (`grep -r "Session\b" eidolon/` returns nothing in code, only in commit/git history)
- [ ] PRD/ROADMAP updated if scope changed: not needed; the rename was already in PRD/ROADMAP via "engagement" language
- [ ] Diagram updated if architecture changed: re-render `docs/diagrams/session-lifecycle.d2` → `engagement-lifecycle.d2` in a follow-up task
