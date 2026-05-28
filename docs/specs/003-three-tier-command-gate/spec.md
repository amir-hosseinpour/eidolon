# Spec: Three-tier command gate w/ operator co-sign

Feature ID: 003-three-tier-command-gate
Status: Partially extracted (2026-04-26) — see [docs/BLUEPRINT-V0.1.md](../../BLUEPRINT-V0.1.md)
Created: 2026-04-26

> **Voyageur extraction note (2026-04-26):** The operator co-sign flow —
> Ed25519-signed operator approvals, operators.json registry, the
> /authorizations endpoints, the prohibited-tier "create AUTHZ then approve"
> dance — was moved to the Voyageur fork. v0.1 Eidolon keeps the three-tier
> taxonomy on scope tokens (autonomous / confirm / prohibited): autonomous
> dispatches go through, confirm-tier requires confirm_token header,
> prohibited-tier hard-blocks with HTTP 403 tier_prohibited. There is no
> operator-cosign workflow inside Eidolon. The Decision Forks layer (see
> docs/BLUEPRINT-V0.1.md and Spec 007) handles strategic confirm moments
> via 5 fork types — that is a different mechanism with different intent.
Updated: 2026-04-26
Spec author: Damion
Implementation owner: Damion

## Problem statement

Spec 001 ships scope-token verification at `/tools/dispatch` with three tier names (autonomous / confirm / prohibited), but **prohibited-tier dispatches** today behave like confirm-tier: the orchestrator only checks the token's tier, not whether a second operator (the Rules-of-Engagement holder) actually approved the call. That collapses the whole differentiator.

The pattern that no peer ships — Codex, Claude Code, PentAGI, Microsoft AGT — is "prohibited tier requires a different operator's signature before the dispatch completes." This spec adds the **pending-authorization** workflow, the **operator identity registry**, and the **CLI approve verb** that close that gap.

The implementation is deliberately minimal for v0.1 (per BUILD-PLAN risk #1):
- Operator identity = config-file list of Ed25519 pubkeys, no rotation.
- Approval = Ed25519 signature over the pending-authorization id.
- Requester identity at dispatch time = unsigned `x-operator` header (documented gap, Spec 006 fixes).
- Audit chain anchoring = stub events; Spec 004 makes the chain real.

## User stories

- US-1. As an operator, I want to attempt a prohibited-tier tool call and receive a `pending_authorization_id` so a second operator can review and approve.
- US-2. As an RoE-holder operator, I want `eidolon authz approve <id>` to sign-off on the request with my Ed25519 key and unblock the dispatch.
- US-3. As the system, I want to refuse self-approval (the requester cannot also be the approver) so split-knowledge is enforced.
- US-4. As an auditor, I want every prohibited-tier dispatch to emit four ordered events (`pending`, `approved` or `denied`, `completed` or `expired`) so the chain reconstructs the decision.
- US-5. As an operator, I want pending authorizations to expire after 15 minutes by default so a stale approval can't be replayed days later.

## Acceptance criteria

- AC-1. `POST /v1/tools/dispatch` with a `tier=prohibited` scope token, **without** `authz_id` in the body, returns `202 Accepted` with `{pending_authorization_id, expires_at, requires: "operator_cosign"}`. The dispatch does not execute. The operator registry must contain the requester's name.
- AC-2. `POST /v1/authorizations/{id}/approve` with body `{operator: "<name>", signature: "<b64>"}` verifies the Ed25519 signature against the registered pubkey, marks the authorization `approved`, records `approver` and `approved_at`. Returns `200` with the updated record.
- AC-3. The same operator cannot approve their own request: if `operator == requested_by`, the endpoint returns `409` with `{reason: "self_approval_forbidden"}`.
- AC-4. Re-issuing `POST /v1/tools/dispatch` with `authz_id` set to an `approved` authorization completes the dispatch (returns `200` with the same `ToolDispatchResponse` shape as autonomous-tier dispatch). Each step (`pending`, `approved`, `completed`) emits an audit event with `engagement_id`, `authz_id`, `operator`, `tool_id`, `target`, `action`, and (for `completed`) `dispatch_id`.
- AC-5. Authorizations expire 15 minutes after creation by default (configurable via `EIDOLON_AUTHZ_TTL_SECONDS`). Re-dispatch with an expired `authz_id` returns `403` with `{reason: "authz_expired"}` and emits an `authz_expired` audit event.
- AC-6. `GET /v1/authorizations/{id}` returns the authorization record (status, requester, approver, timestamps). `GET /v1/engagements/{id}/authorizations` lists all authorizations for an engagement.
- AC-7. `eidolon authz list <engagement_id>` prints the pending and recently-decided authorizations as a table.
- AC-8. `eidolon authz approve <id> --as <operator> --key <path-to-ed25519-private-key>` signs the canonical payload `{"authz_id": id, "decision": "approve"}`, posts the signature, prints the updated record. Exit code 1 on rejection.
- AC-9. Operator registry loads from `$EIDOLON_HOME/operators.json` on first use. Schema: `[{name: str, pubkey: str (b64)}]`. Missing file returns an empty registry.

## Out of scope

- Operator key rotation. (Add a key, edit the file. v0.2 ships a rotation flow.)
- Hardware tokens (FIDO/YubiKey). v0.2.
- Quorum approval (n-of-m). v0.2.
- Time-of-day / business-hours policies. Cut.
- Signed requester identity. v0.1 trusts `x-operator` header; tampering this header lets an attacker pretend to be operator B initiating a request, but does NOT let them approve it (signature still required from a different operator's private key). Documented gap, fixed in Spec 006.
- Real hash-chain anchoring. Audit stub emits events; Spec 004 wires the chain.
- Approve via web UI. CLI only in v0.1.

## Constitution gates

- [x] CON-1 — control plane is the product. Co-sign workflow is a control-plane primitive.
- [x] CON-2 — every action requires per-call authorization. Prohibited tier now actually enforces it.
- [x] CON-7 — operator co-sign at prohibited tier. This spec implements the rule.
- [x] CON-12 — spec includes constitution gates section.

## Open questions

- Should `requested_by` be stamped on the scope token at issuance time (signed) instead of the unsigned dispatch header? Yes for production. Deferring to Spec 006 because it requires an `--operator` flag on `eidolon engagement scope` and re-issuing every test scope token. v0.1 ships the workflow; v0.2 hardens the inputs.
- Should expired authorizations auto-deny the dispatch or require an explicit re-dispatch? v0.1: explicit re-dispatch returning the expired error so the operator notices. Auto-extend would mask staleness.

## References

- Spec 001 — `docs/specs/001-scope-token-end-to-end/`
- Spec 002 — `docs/specs/002-engagement-lifecycle-cli/`
- ADR 0008 — `docs/adr/0008-control-plane-only-byo-vm.md`
- Constitution — `docs/constitution.md`
- BUILD-PLAN — `docs/BUILD-PLAN-V0.1.md`, "Spec 003" + "Honest list of risks #1"
