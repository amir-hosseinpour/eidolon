# Spec: Scope token end to end

Feature ID: 001-scope-token-end-to-end
Status: Approved
Created: 2026-04-26
Updated: 2026-04-26
Spec author: Damion
Implementation owner: Damion

## Problem statement

The orchestrator already has scope token plumbing (`eidolon/orchestrator/lib/scope.py`), but the token shape, the issuance flow, and the per-call enforcement are not aligned with the v0.1 contract. The token must bind one **engagement** to a set of CIDRs, a set of permitted actions, a maximum tier, and an expiry, in a single signed payload. Every tool router must enforce all four checks plus a revocation lookup. Today the orchestrator uses "session" terminology, has no tier in the token, has no revocation, and has no `/v1/engagements/{id}/scope-token` endpoint.

## User stories

- US-1: As an operator, I want to call `POST /v1/engagements/{id}/scope-token` with a CIDR list, permitted actions, a tier, and a TTL, and receive a JWT that binds those values to the engagement.
- US-2: As an operator, I want every tool router to reject calls with an invalid, expired, revoked, mismatched-engagement, out-of-CIDR, out-of-action, or over-tier scope token, with a clear failure code and reason.
- US-3: As an operator, I want to revoke a previously issued scope token without restarting the orchestrator.

## Acceptance criteria

- AC-1. `POST /v1/engagements/{engagement_id}/scope-token` with body `{targets: ["10.0.0.0/24"], permits: ["recon.active"], tier: "confirm", ttl_seconds: 28800}` returns `201` and `{token: "<JWT>", jti: "<uuid>", expires_at: <epoch>, engagement_id: "<id>"}`. JWT payload contains: `sub=engagement_id`, `jti`, `iat`, `exp`, `scope.allowed_cidrs=["10.0.0.0/24"]`, `scope.allowed_actions=["recon.active"]`, `scope.tier="confirm"`. Signed HS256 with `EIDOLON_HMAC_SECRET`.
- AC-2. Every tool router endpoint accepts an `x-scope-token` header and runs, in order: signature verify → engagement match → revocation lookup → expiry check → CIDR target check → action check → tier check. Each failure produces a structured error with HTTP status and a stable reason string:
  - Bad signature or malformed JWT: `401`, `reason=token_invalid`
  - Token expired: `401`, `reason=token_expired`
  - Token revoked: `401`, `reason=token_revoked`
  - Token engagement does not match path engagement: `403`, `reason=engagement_mismatch`
  - Target outside `allowed_cidrs`: `403`, `reason=target_out_of_scope`
  - Action not in `allowed_actions`: `403`, `reason=action_out_of_scope`
  - Tool tier exceeds token tier: `403`, `reason=tier_exceeded`
- AC-3. `POST /v1/engagements/{engagement_id}/scope-token/revoke` body `{jti: "<uuid>"}` returns `204` and any subsequent verification of that JTI returns `401 reason=token_revoked`.
- AC-4. CIDR boundary case: target IP that sits one bit outside the CIDR network must be rejected. (E.g. `allowed_cidrs=["10.0.0.0/24"]` rejects `10.0.1.1`.)
- AC-5. Tier ordering enforced: token tier `autonomous` permits autonomous tools only; `confirm` permits autonomous and confirm; `prohibited` permits all three (subject to the operator co-sign in Spec 003 — out of scope for 001).

## Out of scope

- Token rotation. (Issue a new token, revoke the old.)
- Asymmetric signing (HS256 only for v0.1).
- Distributed revocation list (in-memory set fine; revocation is per-orchestrator-process for v0.1).
- Operator co-sign at the prohibited tier (Spec 003).
- Audit log emission per call (Spec 004 — but this spec writes to a stub audit hook so 004 can plug in).

## Constitution gates

- [x] CON-4 — every tool call mediated by a scope token. Applies because this spec defines the verification contract.
- [x] CON-5 — every command has a tier. Applies because tier check is part of verification.
- [x] CON-7 — every authorized action appended to audit log. Applies via stub hook; full implementation lands with Spec 004.
- [x] CON-12 — spec includes constitution gates section. This section.

## Open questions

None. CIDR boundary semantics use `ipaddress.ip_network(strict=False).contains(ip)`. Revocation store is process-local. JTI is a UUID4.

## References

- ADR 0008 (control plane only, BYO VM) — `docs/adr/0008-control-plane-only-byo-vm.md`
- Constitution rules CON-4, CON-5, CON-7, CON-12 — `docs/constitution.md`
- Existing scaffold: `eidolon/orchestrator/lib/scope.py`, `eidolon/orchestrator/app/routers/tools.py`, `eidolon/orchestrator/app/routers/sessions.py`
