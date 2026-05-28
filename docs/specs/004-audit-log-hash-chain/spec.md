# Spec: Audit log hash chain

Feature ID: 004-audit-log-hash-chain
Status: Approved
Created: 2026-04-26
Updated: 2026-04-26
Spec author: Damion
Implementation owner: Damion

## Problem statement

Specs 001–003 emit audit events through a stub (`audit_stub.emit_scope_audit`) that just logs to stderr. There is no append-only file, no hash chain, no verification command, and the Certificate of Destruction (Spec 002) embeds placeholder zeros for `audit_head_at_open` / `audit_head_at_close`. Without a real chain, the cert is unsigned dust.

This spec wires the chain. v0.1 ships a **single global hash-chained file per UTC day** at `$EIDOLON_HOME/audit/audit-YYYY-MM-DD.jsonl`, opened with `O_APPEND`, written one JSON entry per line. Each entry carries `prev_hash` and `hash`; the chain is verifiable end-to-end. The Cert of Destruction is upgraded to embed the **real** head hash at engagement open and at engagement close, signed by the existing Ed25519 audit key.

What v0.1 deliberately defers (per BUILD-PLAN risk #3):
- Daily rotation as a real cron-driven event. v0.1 rotates implicitly: when the calendar day changes, the next append opens a new file whose first entry's `prev_hash` is the prior file's tail hash.
- GPG-signed segment closes. v0.1 signs the cert; signing every segment lands in v0.2.
- chattr +a / TLS rsyslog. Voyageur ships those.
- Distributed log shipping. Out of scope.

## User stories

- US-1. As an operator, I want every prohibited dispatch + every scope-token verification + every authz approval written to a hash-chained log so I can prove what happened.
- US-2. As an auditor, I want `eidolon audit verify` to walk the chain and tell me OK or the seq of the first broken link.
- US-3. As a customer, I want a Certificate of Destruction to embed real head hashes from the audit chain at engagement open and close.
- US-4. As an operator, I want `eidolon audit head` to show the current chain head hash so I can pin it for external attestation.
- US-5. As a developer, I want the chain to roll over automatically at UTC midnight without an explicit cron job in v0.1.

## Acceptance criteria

- AC-1. `AuditChain.append(event)` writes one entry to `$EIDOLON_HOME/audit/audit-YYYY-MM-DD.jsonl` (UTC date). Entry shape: `{seq, ts, event, engagement_id, operator_id?, action?, target?, tier?, dispatch_id?, authz_id?, jti?, reason?, prev_hash, hash}`. `hash = sha256(prev_hash || canonical_json(entry_minus_hash))` where canonical JSON is `sort_keys=True, separators=(",",":")`.
- AC-2. `seq` increments monotonically across the lifetime of the chain (does NOT reset at midnight). Successive segments link via the prior file's tail-hash carried into the next file as the first entry's `prev_hash`.
- AC-3. `AuditChain.head()` returns the most recent entry's `hash` from the most recent segment, or the bootstrap zero-hash (`"0"*64`) if no entries exist.
- AC-4. `AuditChain.verify(path)` walks a segment file and returns `(ok, broken_seq)`. Tampering with any byte of any entry must cause `ok=False`.
- AC-5. Audit directory is created with mode `0700`. Files are opened with `O_APPEND | O_CREAT | O_WRONLY`. (POSIX append; Voyageur Logger VM adds `chattr +a`.)
- AC-6. `Engagement` records the head hash at open in a new field `audit_head_at_open`. Cert of Destruction embeds `audit_head_at_open` (from engagement record) and `audit_head_at_close` (head at erase time). The Ed25519 signature on the cert covers both, exactly like Spec 002 already does.
- AC-7. `eidolon audit head` prints `{head, segment, seq}` JSON. `eidolon audit verify [--segment YYYY-MM-DD]` walks the segment (or current day if omitted) and prints `{ok, broken_seq}`. Exit code 1 if broken.
- AC-8. `audit_stub.emit_scope_audit` is replaced with `audit.emit_audit(event)` that delegates to `AuditChain`. All call sites in `engagements.py`, `tools.py`, `authorizations.py` use the new function.
- AC-9. A deliberate-tamper test: write 5 entries, flip a byte in entry 3, run verify, get `ok=False` and `broken_seq=3`.

## Out of scope

- Daily-segment GPG signing (cert signs at erase time; per-segment signing is v0.2).
- Tamper-evident filesystem features beyond POSIX append.
- Distributed log shipping / SIEM integration.
- Per-engagement segment files (single global chain in v0.1).
- Compaction / archival.
- Non-UTC daily boundaries.

## Constitution gates

- [x] CON-1 — control plane is the product. Audit chain is foundational.
- [x] CON-3 — every scope-mediated call must be auditable. Now actually enforced.
- [x] CON-9 — Cert of Destruction anchored to audit head hashes. AC-6 implements anchoring.
- [x] CON-12 — gates section in spec.

## Open questions

- Does the chain need to survive process restart with no replay? Yes for v0.1: chain reads from disk on each `append`, so process restart resumes correctly. Performance acceptable for DefCon demo (single-digit ops/sec).
- Should `verify` cross segment boundaries? Yes — `eidolon audit verify --range YYYY-MM-DD..YYYY-MM-DD` is a v0.2 ticket. v0.1 verifies one segment at a time.

## References

- Spec 002 — `docs/specs/002-engagement-lifecycle-cli/`
- Spec 003 — `docs/specs/003-three-tier-command-gate/`
- Constitution CON-3, CON-9 — `docs/constitution.md`
- BUILD-PLAN — `docs/BUILD-PLAN-V0.1.md`, "Spec 004"
