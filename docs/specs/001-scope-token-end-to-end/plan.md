# Plan: Scope token end to end

Spec: `./spec.md`
Status: Approved
Updated: 2026-04-26

## Approach

Extend the existing `ScopeDocument` with a `tier` field. Move from `Session` to `Engagement` terminology (rename, not duplicate). Add a `jti` to the JWT payload and a process-local `RevocationStore`. Add a single `engagements` router that exposes scope-token issuance and revocation. Centralize verification in a `verify_scope_token` function that returns a typed `VerifiedToken` or raises a typed `ScopeError`; tool routers call it via a FastAPI dependency. Each error type maps 1:1 to a `(status_code, reason)` tuple.

## Architecture

- Touched: `eidolon/orchestrator/lib/scope.py`, `eidolon/orchestrator/lib/sessions.py` (rename → `engagements.py`), `eidolon/orchestrator/app/routers/sessions.py` (rename → `engagements.py`), `eidolon/orchestrator/app/routers/tools.py`, `eidolon/orchestrator/app/main.py`, `tests/test_smoke.py` (update endpoint paths), `tests/conftest.py` (no change).
- Added: `eidolon/orchestrator/lib/revocation.py`, `eidolon/orchestrator/lib/audit_stub.py` (stub hook for Spec 004), `eidolon/orchestrator/app/dependencies.py` (FastAPI dependency for scope verify), `tests/test_scope_token.py` (per-AC tests).
- Removed: nothing (renames preserve history).

## Data model

`ScopeDocument` (Pydantic) gains a `tier` field:

```python
ScopeTier = Literal["autonomous", "confirm", "prohibited"]

class ScopeDocument(BaseModel):
    allowed_cidrs: list[str]
    allowed_actions: list[ScopeAction]
    tier: ScopeTier
    rules_of_engagement: str = ""
    expires_at: int | None = None
```

JWT payload (HS256):

```json
{
  "sub": "<engagement_id>",
  "jti": "<uuid4>",
  "iat": <epoch>,
  "exp": <epoch>,
  "scope": {
    "allowed_cidrs": ["10.0.0.0/24"],
    "allowed_actions": ["recon.active"],
    "tier": "confirm",
    "rules_of_engagement": "...",
    "expires_at": <epoch>
  }
}
```

`VerifiedToken`:

```python
@dataclass(frozen=True)
class VerifiedToken:
    engagement_id: str
    jti: str
    scope: ScopeDocument
    iat: int
    exp: int
```

`ScopeError`:

```python
class ScopeError(Exception):
    status_code: int
    reason: str  # "token_invalid" | "token_expired" | "token_revoked" |
                 # "engagement_mismatch" | "target_out_of_scope" |
                 # "action_out_of_scope" | "tier_exceeded"
```

## Contracts

### API endpoints

`POST /v1/engagements/{engagement_id}/scope-token`

Request:
```json
{
  "targets": ["10.0.0.0/24"],
  "permits": ["recon.active"],
  "tier": "confirm",
  "ttl_seconds": 28800,
  "rules_of_engagement": "DefCon demo"
}
```

Response (201):
```json
{
  "token": "eyJhbGciOi...",
  "jti": "f1e2d3c4-...",
  "engagement_id": "ENG-...",
  "expires_at": 1714348800
}
```

Errors: `404` if engagement not found, `409` if engagement is closed.

`POST /v1/engagements/{engagement_id}/scope-token/revoke`

Request:
```json
{ "jti": "f1e2d3c4-..." }
```

Response: `204 No Content`.

`POST /v1/tools/dispatch` (existing; re-uses dependency)

Adds tier-exceeded check using `scope.tier`. Returns the structured errors above on failure.

### Internal: FastAPI dependency

```python
async def require_scope_token(
    engagement_id: str,
    x_scope_token: str = Header(...),
) -> VerifiedToken:
    try:
        return verify_scope_token(x_scope_token, expected_engagement=engagement_id)
    except ScopeError as e:
        raise HTTPException(status_code=e.status_code, detail={"reason": e.reason})
```

### Events / log lines

Stub audit hook called from `verify_scope_token` on success and on each failure. Hook signature:

```python
def emit_scope_audit(event: dict[str, Any]) -> None: ...
```

For 001 the hook writes one line of structlog JSON. Spec 004 replaces this with the hash-chained writer.

## Migrations

Rename `Session` → `Engagement` in code; rename `/v1/sessions/...` → `/v1/engagements/...` in routes. Tests update with the rename. No DB migration in 001 (in-memory store still). Spec 002 adds SQLite.

## Security review

- Threats considered:
  - **Replay across engagements** — token from engagement A used against engagement B. Mitigated by engagement match check.
  - **Replay after revoke** — explicit revocation list, checked first.
  - **Replay after expiry** — PyJWT enforces `exp`; we map `ExpiredSignatureError` → 401 token_expired.
  - **Tier escalation** — token tier is a hard ceiling; tool tier ≤ token tier or 403.
  - **CIDR confusion** — boundary case test (AC-4); use `ipaddress.ip_network(strict=False).hosts()` semantics, not string prefix match.
  - **Algorithm confusion attack** — PyJWT `decode(algorithms=["HS256"])` enforces algorithm; do not accept `none` or RS256.
- Scope token enforcement: yes, every tool router via `require_scope_token` dependency. The dependency is the only way in.
- Command tier: this spec sets the *ceiling* via `scope.tier`. Spec 003 adds the operator co-sign at the prohibited tier.
- Audit log entries emitted: one per verify call, success or failure (stubbed; hash-chained in Spec 004).

## Test strategy

`tests/test_scope_token.py` (new):

- Unit: `verify_scope_token` rejects bad signature, expired, revoked, engagement mismatch, target out of scope, action out of scope, tier exceeded — one parametrized test per `(reason, fixture)` pair.
- Unit: CIDR boundary — target one bit outside network is rejected.
- Integration via `TestClient`: issuance endpoint returns 201 with all expected fields; revocation endpoint returns 204; subsequent verify of revoked JTI returns 401 token_revoked; closed engagement issuance returns 409.
- Integration: end-to-end happy path through `POST /v1/tools/dispatch` with a valid token.

`tests/test_smoke.py` (existing) updated for the rename: `/v1/sessions/...` → `/v1/engagements/...`. Same coverage maintained.

`make verify` is the gate.

## Risks and mitigations

1. **Renaming churn breaks something subtle.** Mitigation: small repo, full test run after each step. `make verify` must stay green at every commit.
2. **JTI collisions if RNG is bad.** Mitigation: `uuid.uuid4()`; trust stdlib.
3. **Revocation store is process-local — orchestrator restart loses revocations.** Documented limitation for v0.1; v0.2 moves to SQLite. Mitigation: ROADMAP entry plus a comment in `revocation.py`.

## Alternatives considered

- **Add `tier` to JWT but keep ScopeDocument unchanged.** Rejected. The model is the contract; bifurcating between JWT-level and document-level fields hides the tier from the Pydantic validation.
- **Keep `Session` terminology and add `Engagement` later.** Rejected per CLAUDE.md "no backwards-compat hacks." Rename now while the surface is small.
- **Asymmetric signing (RS256/EdDSA).** Rejected for v0.1; HS256 is enough for a single orchestrator. Asymmetric is a v0.3 ask when multiple orchestrator pods need to share keys without sharing secrets.
- **Cookie-based tokens.** Rejected. CLI tooling and machine clients prefer header.

## Out of scope (technical)

- Operator co-sign at prohibited tier (Spec 003).
- Hash-chained audit log writer (Spec 004 — Spec 001 emits to a stub).
- Persistent engagement store (Spec 002 — Spec 001 keeps the in-memory store).
- LLM router redaction (Spec 005).
