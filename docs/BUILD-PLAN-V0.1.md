# Eidolon v0.1 Build Plan

Status: **SUPERSEDED (2026-04-26)** by [docs/BLUEPRINT-V0.1.md](BLUEPRINT-V0.1.md). The framing in this document — Eidolon as a compliance/governance control plane built around Cert of Destruction and operator co-sign — was wrong. The real product is a templated multi-VM workspace orchestrator for AI-driven offsec engagements; compliance overlay is downstream forks's job. See BLUEPRINT-V0.1.md for the actual plan.

Created: 2026-04-26
Deadline: v0.1 ship within 1 week from start
Owner: Damion

## Verdict

Build it. Both research streams agreed. The combination of (a) per-engagement identity binding, (b) command-tier gate with operator authorization at the prohibited tier, (c) LUKS volume + cryptographic erase + Certificate of Destruction, and (d) hybrid LLM routing with redaction, in a pentest workflow, is not shipped by any project surveyed. Closest competitors and what they miss:

- **PentAGI** (vxcontrol/pentagi, 15.8k stars, MIT) — pentest agent stack with multi-agent execution. Zero governance. No scope tokens, no engagement boundary, no audit attestation, no destruction proof. The April 2026 Checkpoint Research write-up on HexStrike-AI being weaponized for zero-day exploitation is the existence proof for the gap: "AI pentest agent without governance" is not a product, it's a liability.
- **Microsoft Agent Governance Toolkit** (released 2026-04-02, MIT) — closest structural match. Has execution rings, capability sandboxing, trust scoring (0–1000), append-only hash-chained audit logs, Ed25519 plugin signing, quorum approval. Has zero concept of a time-bounded engagement, zero LUKS / crypto-erase / destruction certificate workflow, zero pentest tool integration, zero "prohibited tier requires RoE-holder co-sign" pattern.
- **NodeZero / Pentera** — commercial proprietary SaaS. Vendors won't open-source the governance layer because that's the moat. Eidolon ships it open-source; downstream forks sells the managed VMs and firm SOPs on top.
- **E2B / Daytona / OpenHands** — sandboxed code execution platforms. Solve the VM problem already. Reinforces the scope cut below.

What is NOT novel (and the plan acknowledges this honestly):

- Scope tokens as a concept — capability-based security and OAuth scopes are decades old. Novel piece is the binding (engagement UUID + CIDR + tier + expiry) and end-to-end enforcement at every tool call.
- Three-tier command gating — Codex, Claude Code, and Microsoft AGT all have something in this shape. Novel piece is the prohibited tier requiring operator (RoE-holder) authorization, which mirrors the actual legal workflow of authorized testing.
- Hash-chained append-only audit logs — standard practice. Novel piece is what gets logged (every scope-token-bearing call) and how it's anchored (daily GPG-signed rotation feeding the Cert of Destruction).
- VM isolation — solved many ways. The novel piece below is *not* "we ship VMs"; we don't.

## Sharp scope decision: cut the six VMs from v0.1

Current `vms/` directory has six empty subdirectories (Engagement, Logger, Recon, Web, Internal, Wireless). VM provisioning is a solved problem (Proxmox SDN, Terraform, Packer; or E2B / Daytona / Firecracker for cloud). The hard problem and the moat is the **control plane**. So:

- **Eidolon v0.1 (open source, MIT)** = control plane only. Scope tokens, three-tier command gate, audit hash chain, engagement lifecycle CLI, hybrid LLM router with redaction. BYO VM — operators wire their own runtime (Proxmox, vSphere, libvirt, Docker, bare metal) via a `HypervisorBackend` adapter interface defined in v0.2.
- **A managed downstream fork** = Eidolon + managed VM provisioning (Proxmox SDN per-engagement VNETs, LUKS volume orchestration, Logger VM with chattr-immutable rsyslog) + firm-specific RoE templates, evidence handling SOPs, and the pre-loaded MSA scope language.

This re-positions Eidolon from "a pentest VM appliance" to "the governance layer for AI-driven offensive work, runtime-agnostic." That is the defensible position. Anyone can ship a VM template; nobody else is shipping the engagement-scoped identity model.

## Fork vs. build call: build fresh

- Don't fork PentAGI. Fundamentally different trust model. PentAGI's execution layer assumes the agent should run; Eidolon assumes every action requires per-call authorization. Refactoring to engagement-scoped identity is harder than starting clean, and the FastAPI codebase that already exists (~150 lines of scope-token + tier-gate logic) is correct.
- Don't fork Microsoft AGT. Closer structural fit, but the engagement-binding is *the entire product*, and AGT has no concept of it. Refactor cost > build cost. Cite their patterns (execution rings, hash-chain, Ed25519 signing) in ADRs as prior art; do not depend on the package.
- Build fresh on what's already there: FastAPI + Pydantic v2 + PyJWT HS256 scope tokens + LiteLLM router. The existing `orchestrator/lib/scope.py` and `orchestrator/app/routers/tools.py` are the core; everything else extends from them.

## Pre-flight: package and repo hygiene (must complete before any spec work)

P-1. Move `cli/` and `orchestrator/` under a top-level `eidolon/` package directory. Update `pyproject.toml`:
 - `[tool.setuptools.packages.find] where = ["."]` and explicit `include = ["eidolon*"]`
 - `[project.scripts] eidolon = "eidolon.cli.main:main"`
 - Re-run `pip install -e .` and verify `eidolon --help` works.

P-2. Delete leftover `shroud.egg-info/` directory (artifact from pre-rename install).

P-3. Add a `Makefile` target `make verify` that runs: `ruff check`, `mypy orchestrator cli`, `pytest -x`, and a smoke test of `eidolon --help`. CI will call this single target.

P-4. Wire GitHub Actions: a single workflow that runs `make verify` on push and PR. Don't bikeshed: ubuntu-latest, Python 3.12, no matrix.

P-5. Add `docs/constitution.md` distilling the 7 (currently 5; 0003 and 0005 are missing — backfill or renumber) ADRs into enforceable rules. Each rule has an ID (CON-1, CON-2, ...), a one-sentence statement, the ADR it derives from, and how it's enforced (test, lint, runtime check, or human review).

P-6. Add ADR-0008: "v0.1 scope = control plane only, BYO VM." Cite the research findings from this document. Mark ADR-0001 (fork from homelab blueprint) as superseded by 0008 to the extent that the homelab VMs are no longer in v0.1 scope.

P-7. Update `PRD.md` to reflect the scope cut. Out-of-scope section gets the six VMs explicitly. ROADMAP.md gets a new top section "v0.1 = control plane only" and the six-VM bundle becomes downstream forks-internal.

## Specs to write and implement, in dependency order

Each spec follows the SDD template scaffold already in `.specify/templates/`. Each gets `spec.md`, `plan.md`, `tasks.md` under `docs/specs/NNN-feature-name/`. Tests-first per template: failing test, then implementation. No spec is "done" until `make verify` passes and a manual smoke test confirms the acceptance criteria.

### Spec 001: scope-token-end-to-end

Path: `docs/specs/001-scope-token-end-to-end/`

- **Problem.** Scope token logic exists in `orchestrator/lib/scope.py` but is not enforced at every tool-call entry point and there is no client-side issuance flow that binds tokens to a CIDR + engagement UUID + tier + expiry in one issuance.
- **Acceptance criteria.**
 - AC-1. `POST /engagements/{id}/scope-token` issues a token containing `{engagement_id, targets: [CIDR...], permits: [action...], tier: <max-allowed>, exp}` signed HS256.
 - AC-2. Every tool router (`/tools/*`) verifies the token, asserts target match (CIDR contains), action match (permits), tier match (≤ requested), and engagement match. Failure returns 403 with a structured reason.
 - AC-3. Token expiry returns 401 with `reason: token_expired`.
 - AC-4. Replay-after-revoke is rejected (revocation list lookup; in-memory set is fine for v0.1).
- **Out of scope.** Token rotation. Multi-region. Public-key signing (HS256 only for v0.1).
- **Touched files.** `orchestrator/lib/scope.py`, `orchestrator/app/routers/scope.py` (new), all `orchestrator/app/routers/*.py` tool endpoints. Tests in `tests/test_scope_token.py` covering happy path, every failure mode, and at least one CIDR boundary case (target outside scope).

### Spec 002: engagement-lifecycle-cli

Path: `docs/specs/002-engagement-lifecycle-cli/`

- **Problem.** No CLI exists for the engagement lifecycle (open, scope, run, close, erase, attest). Operators currently can't drive the system end-to-end without curl.
- **Acceptance criteria.**
 - AC-1. `eidolon engagement open --client X --rules-of-engagement path/to/roe.md` creates an engagement record, returns the engagement UUID.
 - AC-2. `eidolon engagement scope <id> --target 10.0.0.0/24 --permit recon --tier confirm --ttl 8h` mints a scope token bound to that engagement and prints it.
 - AC-3. `eidolon engagement close <id>` marks the engagement closed; further token issuance for that ID is rejected.
 - AC-4. `eidolon engagement erase <id>` writes a destruction event into the audit chain, returns a Cert of Destruction (signed JSON, plus a stub PDF in v0.1) referencing the LUKS volume UUID placeholder. (Real LUKS erase lives in downstream forks; v0.1 emits the *attestation*, the volume itself is BYO.)
 - AC-5. `eidolon engagement show <id>` prints engagement state, scope tokens issued, audit chain head hash.
- **Out of scope.** Interactive REPL. Web UI. Multi-engagement views (single engagement at a time in v0.1).
- **Touched files.** `eidolon/cli/main.py`, `eidolon/cli/engagement.py` (new), `orchestrator/app/routers/engagements.py` (new). Persistence: SQLite at `~/.eidolon/state.db`, schema migration via alembic stub. Tests in `tests/test_engagement_cli.py`.

### Spec 003: three-tier-command-gate

Path: `docs/specs/003-three-tier-command-gate/`

- **Problem.** `orchestrator/app/routers/tools.py` already declares the three frozen sets (autonomous, confirm, prohibited) but the *prohibited* tier has no operator-authorization workflow. The behavior that differentiates Eidolon from Codex / Claude Code / Microsoft AGT is the prohibited-tier-requires-RoE-holder-cosign pattern; without it, this spec is just a re-skin.
- **Acceptance criteria.**
 - AC-1. A call to a prohibited-tier tool with a `tier=prohibited` scope token returns `202 Authorization Required` with a `pending_authorization_id`.
 - AC-2. `eidolon authz approve <pending_id>` from a different operator (the RoE holder, identified by signed approval token configured at engagement open time) flips the pending request to authorized and lets the tool call complete.
 - AC-3. The same operator cannot approve their own request (split-knowledge enforcement at the CLI layer).
 - AC-4. Audit log records: original request, pending event, approver identity, approval timestamp, completion event. All four entries hash-chained.
 - AC-5. Authorization expires (default 15 min); expired authz requires re-approval.
- **Out of scope.** Hardware tokens (FIDO/YubiKey). Quorum > 2. Time-of-day policies.
- **Touched files.** `orchestrator/app/routers/tools.py`, `orchestrator/lib/authorization.py` (new), `orchestrator/lib/operators.py` (new — operator identity + signed approval tokens), `eidolon/cli/authz.py` (new). Tests in `tests/test_command_tier_gate.py` covering all five ACs plus self-approval rejection.

### Spec 004: audit-log-hash-chain

Path: `docs/specs/004-audit-log-hash-chain/`

- **Problem.** Audit logging is referenced in ADRs but no implementation exists. Every call mediated by scope tokens needs to land in an append-only hash-chained log. Microsoft AGT proves this is table stakes; Eidolon's differentiator is what gets logged (engagement-scoped events) and the daily GPG-signed rotation that anchors the Cert of Destruction.
- **Acceptance criteria.**
 - AC-1. Every scope-token-bearing call writes one entry: `{seq, ts, engagement_id, operator_id, action, target, tier, result, prev_hash, hash}`. Hash is `sha256(prev_hash || canonical_json(entry_minus_hash))`.
 - AC-2. Verification command `eidolon audit verify <engagement_id>` walks the chain and returns OK or the index of the first broken link.
 - AC-3. Daily rotation: at UTC midnight, current chain segment is closed with a tail entry, GPG-signed (Ed25519 in v0.1, key generated on first run, stored at `~/.eidolon/keys/audit.ed25519`), and a new segment starts with the previous tail-hash as `prev_hash`.
 - AC-4. Cert of Destruction (Spec 002, AC-4) embeds: engagement UUID, head hash at engagement open, head hash at engagement close, GPG signature over both.
 - AC-5. The audit log file is opened with O_APPEND and the directory is mode 0700. (Real chattr +a is downstream forks-side on the Logger VM; v0.1 uses POSIX append + permissions.)
- **Out of scope.** Distributed log shipping. Real-time SIEM integration. Tamper-evident filesystem features beyond POSIX.
- **Touched files.** `orchestrator/lib/audit.py` (new), `orchestrator/middleware/audit.py` (new — FastAPI middleware that wraps every tool router), `eidolon/cli/audit.py` (new). Tests in `tests/test_audit_chain.py` including a deliberate tamper test (flip a byte mid-chain, verify detection).

### Spec 005: hybrid-llm-router-with-redaction

Path: `docs/specs/005-hybrid-llm-router-with-redaction/`

- **Problem.** `orchestrator/litellm-config/router.yaml` declares the model groups but there is no redaction layer between commercial Gemini and the engagement context. Without redaction, sending engagement-scoped data to a commercial model violates the egress-driven architecture promise.
- **Acceptance criteria.**
 - AC-1. Every LLM call goes through a `route(messages, sensitivity_hint)` function that classifies the messages by sensitivity (target IP / hostname / cred / PII / "vanilla coding question") and chooses the model group: vanilla → commercial Gemini; engagement-context → local (WhiteRabbitNeo / Foundation Sec / Qwen Coder).
 - AC-2. If sensitivity is mixed and the operator has not pre-approved commercial routing for this engagement, redaction strips engagement-scoped tokens (CIDR matches, hostname matches, MAC matches) and replaces with stable placeholders before the commercial call. The unredacted version is logged locally.
 - AC-3. The classifier itself runs locally (cheap regex + a small local model fallback). It does not call commercial APIs.
 - AC-4. A `--strict-local` engagement flag set at open time forces all calls to local models regardless of classifier output.
 - AC-5. Audit log entry for every LLM call records: model group, sensitivity classification, redaction applied yes/no, token counts in/out.
- **Out of scope.** Fine-tuning. Embedding cache. Multi-modal.
- **Touched files.** `orchestrator/lib/llm_router.py` (new), `orchestrator/lib/redaction.py` (new), `orchestrator/litellm-config/router.yaml` (already partly there — extend with the routing rule logic). Tests in `tests/test_llm_router.py` with synthetic engagement context, golden-file assertions for redaction output.

## End-to-end smoke test

Path: `tests/test_end_to_end_engagement.py`

- T-EE-1. Open a synthetic engagement against `192.0.2.0/24` (TEST-NET-1).
- T-EE-2. Mint a confirm-tier scope token for `recon`.
- T-EE-3. Call a no-op recon tool (`/tools/echo` returning the request, registered in autonomous tier for the test) and verify scope-token check, audit log entry, hash chain extension.
- T-EE-4. Attempt a prohibited-tier action with a confirm-tier token; verify 403.
- T-EE-5. Mint a prohibited-tier token, attempt the action, get 202; approve from a second operator identity; verify completion and audit chain.
- T-EE-6. Issue an LLM call with engagement-scoped target reference, verify redaction in the routed payload.
- T-EE-7. Close engagement, run erase, verify Cert of Destruction signature validates against the audit head hashes.
- T-EE-8. Run `eidolon audit verify` and confirm chain intact.

## v0.1 release demo dress-rehearsal

After all 5 specs and the smoke test pass:

- Pre-record a 5-minute walk-through of the smoke test, narrating the differentiator at each step.
- Pre-stage one synthetic engagement on a laptop, ready to demo live (open → scope → recon call → prohibited attempt → operator approval → close → cert).
- Tag the repo `v0.1.0`, write release notes that explicitly cite PentAGI and Microsoft AGT as adjacent prior art and state where Eidolon differs (engagement-binding + crypto-erase attestation + RoE-cosign at prohibited tier + redaction-aware hybrid routing).

## Ordering rationale (no time buckets)

Pre-flight (P-1 through P-7) blocks everything because the package layout is broken and the constitution + scope-cut ADR has to land before specs derive from them. Spec 001 blocks 002, 003, 004, 005 because every other spec assumes scope tokens work end-to-end. Spec 002 blocks 003 (CLI authz approve command lives in cli/) and 004 (Cert of Destruction depends on audit head hashes). Spec 003 and 004 can run in parallel after 002 lands. Spec 005 depends only on 001. Smoke test depends on all five. Demo dress-rehearsal depends on smoke test passing.

## Honest list of risks (in priority order)

1. **Operator-identity model is hand-wavy.** ADR-008 needs to specify how operator identities are bootstrapped (signed approval tokens). If this gets bigger than expected, descope to "config-file list of operator pubkeys, no rotation" for v0.1.
2. **Sensitivity classifier is harder than it sounds.** A regex won't catch everything; a local model adds latency. If the classifier is unreliable, the redaction promise weakens. Mitigation: ship `--strict-local` as the documented safe default and let users opt into commercial routing per engagement.
3. **GPG signing UX is friction.** Generating Ed25519 keys on first run and prompting for passphrase will trip non-Linux users. Mitigation: passphrase-less key in v0.1, document the trade-off, plan passphrase + agent integration for v0.2.
4. **One-week deadline is tight if any spec hits an unknown.** Mitigation: every spec has a defined out-of-scope; if the implementation hits a wall, push the wall into out-of-scope rather than slipping the date. v0.1 is allowed to be opinionated and small.
5. **Demo machine fails during a live demo.** Mitigation: pre-record the 5-minute walk-through; if live demo crashes, play the recording.

## What this plan deliberately does NOT do

- Does not ship the six VMs (cut to downstream forks).
- Does not implement real LUKS erase (cut to downstream forks; v0.1 emits the attestation only).
- Does not implement chattr +a, TLS rsyslog, daily GPG rotation on a separate Logger VM (cut to downstream forks; v0.1 uses POSIX append on local disk).
- Does not implement multi-engagement concurrency, web UI, REPL, or any visualization beyond CLI text output.
- Does not implement Claude Code subagent integrations beyond what already exists (subagent invocation works through the standard tool router; no Claude-specific glue in v0.1).
- Does not pursue formal verification, FedRAMP, SOC2, or any compliance regime in v0.1 (cite as v0.5+ in ROADMAP).

## Definition of done for v0.1

- All five specs have spec.md + plan.md + tasks.md and all task ACs are checked.
- `make verify` passes.
- End-to-end smoke test passes.
- Demo dress-rehearsal recording exists.
- PRD + ROADMAP + constitution + ADR-0008 all reflect reality.
- Repo tagged `v0.1.0`.
