# Spec: Engagement lifecycle CLI

Feature ID: 002-engagement-lifecycle-cli
Status: Partially extracted (2026-04-26) — see [docs/BLUEPRINT-V0.1.md](../../BLUEPRINT-V0.1.md)
Created: 2026-04-26

> **downstream forks extraction note (2026-04-26):** The Certificate of Destruction
> portion of this spec — Ed25519-signed cert generation on engagement erase,
> the sign_cert/verify_cert helpers, and the cert response from the /erase
> endpoint — was moved to the downstream forks fork. v0.1 Eidolon erase transitions
> the engagement to status=erased and records audit_head_at_close, but does
> not generate or sign a cert. The remainder of this spec (engagement
> open/scope/close/erase REST shape, CLI surface, audit head capture) stays
> in Eidolon.
Updated: 2026-04-26
Spec author: Damion
Implementation owner: Damion

## Problem statement

There is no CLI surface for the engagement lifecycle. Operators currently can't drive open → scope → close → erase → attest end-to-end without curl. The CLI should match the orchestrator API exactly so that operator runbooks and Claude Code subagent definitions can both call the same verbs. Spec 001 added the engagements API; Spec 002 puts a typed CLI on top and adds the destruction (erase) + attestation (Cert of Destruction) endpoints.

## User stories

- US-1: As an operator, I want `eidolon engagement open --slug X --purpose ctf --rules-of-engagement path` to create an engagement and return the engagement ID.
- US-2: As an operator, I want `eidolon engagement scope <id> --target 10.0.0.0/24 --permit recon.active --tier confirm --ttl 8h` to mint a scope token and print it.
- US-3: As an operator, I want `eidolon engagement close <id>` to mark the engagement closed and reject further token issuance.
- US-4: As an operator, I want `eidolon engagement erase <id>` to write a destruction event into the audit trail and return a Cert of Destruction.
- US-5: As an operator, I want `eidolon engagement show <id>` to print engagement state, the scope tokens issued, and the audit chain head hash.

## Acceptance criteria

- AC-1. `eidolon engagement open --slug s --purpose pentest --rules-of-engagement path/to/roe.md` calls `POST /v1/engagements/start` with a default scope (empty CIDRs/actions; tier `autonomous`) and prints `{engagement_id, status, scope_token, jti, expires_at}` as JSON.
- AC-2. `eidolon engagement scope <id> --target T1 --target T2 --permit recon.active --tier confirm --ttl 8h` calls `POST /v1/engagements/<id>/scope-token` with `{targets: [T1, T2], permits: [...], tier: ..., ttl_seconds: 28800}` and prints the issued token JSON. `--ttl` accepts `8h`, `30m`, `3600s`.
- AC-3. `eidolon engagement close <id>` calls `POST /v1/engagements/<id>/close`. After close, `eidolon engagement scope <id> ...` returns 409 (asserted by the CLI's exit code 1 with the orchestrator's reason printed).
- AC-4. `eidolon engagement erase <id>` calls `POST /v1/engagements/<id>/erase`. The orchestrator: (a) ensures the engagement is closed (closes it if not), (b) emits a destruction event to the audit hook, (c) returns a Certificate of Destruction `{engagement_id, opened_at, closed_at, erased_at, audit_head_at_open, audit_head_at_close, signature}` signed with the orchestrator's Ed25519 audit key. The CLI prints the cert as JSON and writes it to `~/.eidolon/certs/<engagement_id>.json`.
- AC-5. `eidolon engagement show <id>` calls `GET /v1/engagements/<id>` and prints engagement record. Optional `--with-tokens` includes the issued JTIs (without the JWT bodies). Optional `--with-audit-head` includes the current audit chain head hash (stub value in v0.1; real one lands with Spec 004).
- AC-6. `eidolon engagement list` calls `GET /v1/engagements` and prints a table of engagement IDs, slugs, statuses, created_at, closed_at.
- AC-7. The Ed25519 keypair is generated on first orchestrator startup at `~/.eidolon/keys/audit.ed25519` (private) + `audit.ed25519.pub` (public). Permissions 0600 / 0644.

## Out of scope

- SQLite persistence. (Process-local in-memory store carries over from Spec 001; v0.2 migration.)
- Real LUKS volume erase. The Cert of Destruction *attests* destruction; the volume work is BYO via `HypervisorBackend`.
- PDF rendering of the cert. v0.1 emits signed JSON only.
- Cert verification CLI (`eidolon cert verify`). Lands with Spec 004.
- Operator co-sign at prohibited tier (Spec 003).
- `--rules-of-engagement` content parsing — the CLI passes the file's text verbatim to the API as the `rules_of_engagement` field.

## Constitution gates

- [x] CON-1 — control plane is the product. Applies because Cert of Destruction is part of the governance surface.
- [x] CON-9 — Cert of Destruction anchored to audit head hashes. This spec defines the cert shape; head-hash anchoring lands with Spec 004 (placeholder values until then).
- [x] CON-12 — spec includes constitution gates section. This section.

## Open questions

- Cert verification: how does an external party verify a cert without running the orchestrator? v0.1 ships the public key alongside the cert. v0.2 may publish the public key to a well-known URL or offer a `--detached-key` mode.

## References

- Spec 001 — `docs/specs/001-scope-token-end-to-end/`
- ADR 0008 — `docs/adr/0008-control-plane-only-byo-vm.md`
- Constitution — `docs/constitution.md`
