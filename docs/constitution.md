# Eidolon Constitution

Status: Draft v0.1
Last updated: 2026-04-26

The constitution distills the ADRs into enforceable rules. Each rule has an ID, a one-sentence statement, the ADR it derives from, and how it's enforced (test, lint, runtime check, or human review). Specs and PRs cite rule IDs in their **Constitution gates** section to show compliance or justify deviation.

When an ADR and the constitution disagree, the more recent ADR wins and the constitution is updated in the same PR.

## Rules

### CON-1. The control plane is the product

v0.1 ships scope tokens, command-tier gating, audit hash chain, hybrid LLM router, and engagement lifecycle. v0.1 does not ship VMs, real LUKS orchestration, real SDN, or real immutable Logger. Operators bring their own runtime via the `HypervisorBackend` interface.

- Origin: ADR 0008
- Enforcement: PR review, plus the `tests/test_end_to_end_engagement.py` smoke test runs against `NoOpBackend` to prove the control plane is runtime-independent. Any spec adding VM provisioning code to Eidolon core is rejected and routed to downstream forks.

### CON-2. No Anthropic endpoints in the runtime path

The orchestrator, the LiteLLM router, and any backend executor must not call `api.anthropic.com` (or Anthropic's commercial API) from runtime code. Claude is the operator's personal Claude Code session only.

- Origin: ADR 0002
- Enforcement: A unit test asserts the LiteLLM router config has no `anthropic/*` model groups. Code review for new HTTP clients. Constitution gate in any spec touching LLM routing.

### CON-3. Every runtime LLM call goes through the LiteLLM router

No direct calls to a model provider from orchestrator, CLI, or backends. The router is the single chokepoint where redaction, sensitivity classification, and audit logging attach.

- Origin: ADR 0004
- Enforcement: Unit test that imports the orchestrator app and grep-asserts no `httpx.AsyncClient(base_url=...openai.com|gemini...|googleapis...)` outside `eidolon/orchestrator/lib/llm_router.py`. PR review for new HTTP clients.

### CON-4. Every tool call is mediated by a scope token

Tool routers extract the scope token from the request, verify HS256 signature, check engagement match, target match (CIDR contains), action match (in `permits`), and tier match (≤ token tier), or return 403/401. No bypass for "trusted" callers.

- Origin: Spec 001 (and PRD §5.1, §5.3)
- Enforcement: A test per tool router asserts the verify call is the first thing the handler does, and that 401/403 are emitted for the four failure modes (signature, engagement, target, action/tier). Integration test in `tests/test_end_to_end_engagement.py` step T-EE-4 attempts a prohibited-tier action with a confirm-tier token and asserts 403.

### CON-5. Every command has a tier

Every tool registered in the orchestrator declares a tier — `autonomous`, `confirm`, or `prohibited`. No tier defaulting silently. Unknown tools are rejected at registration time.

- Origin: ADR 0007 (CAI patterns), PRD §5.3
- Enforcement: `eidolon/orchestrator/app/routers/tools.py` `_resolve_tier(tool_id)` raises `KeyError` for unknown tools, with a unit test. Tool registry has a typed schema. Lint rule that any `register_tool(...)` call without a `tier=` kwarg is flagged.

### CON-6. The prohibited tier requires operator co-sign

A scope token alone cannot authorize a prohibited-tier call. A second operator (the Rules-of-Engagement holder, identified at engagement open by a registered Ed25519 public key) must approve via `eidolon authz approve <pending_id>` from a different identity. Same-operator self-approval is rejected.

- Origin: ADR 0008 + Spec 003
- Enforcement: Spec 003 acceptance test cases AC-1..AC-5. Constitution gate in any spec proposing to weaken the co-sign requirement.

### CON-7. Every authorized action is appended to the hash-chained audit log

Every scope-token-bearing call writes one entry: `{seq, ts, engagement_id, operator_id, action, target, tier, result, prev_hash, hash}`. Hash is `sha256(prev_hash || canonical_json(entry_minus_hash))`. Daily Ed25519-signed rotation. No structured event bypasses this.

- Origin: PRD §5.5, Spec 004
- Enforcement: FastAPI middleware in `eidolon/orchestrator/middleware/audit.py` wraps every tool router. Unit test asserts the middleware is registered. Tamper test in `tests/test_audit_chain.py` flips a byte mid-chain and asserts `eidolon audit verify` finds it.

### CON-8. Engagement context never crosses to commercial LLMs without redaction or explicit consent

The hybrid LLM router classifies every message by sensitivity. Engagement-scoped tokens (CIDR matches, hostname matches, MAC matches) are stripped before any commercial-model call unless the operator has set `--strict-local=false` AND opted into commercial routing for this engagement at open time. The classifier itself runs locally.

- Origin: ADR 0004, Spec 005
- Enforcement: Spec 005 acceptance test cases AC-1..AC-5. Golden-file redaction tests with synthetic engagement context. Audit log entry per LLM call records redaction state.

### CON-9. The Certificate of Destruction is anchored to audit head hashes

Engagement close emits a Cert of Destruction (signed JSON, plus stub PDF in v0.1) embedding: engagement UUID, head hash at engagement open, head hash at engagement close, Ed25519 signature over both. The cert's validity check walks the audit chain segment between the two head hashes and verifies the signature.

- Origin: ADR 0008, Spec 002, Spec 004
- Enforcement: Spec 002 AC-4 + Spec 004 AC-4. Integration test in `tests/test_end_to_end_engagement.py` step T-EE-7 verifies the cert against the audit head hashes.

### CON-10. Eidolon is MIT-licensed and fork-friendly

Code is MIT. Docs are CC BY 4.0. No GPL in the runtime path. Firm forks (Downstream forks carry these.) are first-class downstream consumers with a stable API contract.

- Origin: ADR 0001
- Enforcement: License check in CI (forbid GPL in `pyproject.toml` dependencies). PR review.

### CON-11. Tests come before implementation

Each spec's `tasks.md` lists failing tests before the implementation tasks that make them pass. PRs that add features without first adding failing tests are sent back. (Bug fixes get a regression test in the same PR.)

- Origin: SDD `.specify/templates/tasks-template.md`
- Enforcement: PR review. The task-template `[P]` markers identify which tests can run in parallel with which implementation tasks.

### CON-12. Every spec has a constitution gate section

`docs/specs/NNN-feature/spec.md` includes a `## Constitution gates` section listing applicable rule IDs and either a check (`yes, complies because…`) or a justification for deviation. Plans that propose new rules update this constitution in the same PR.

- Origin: `.specify/templates/spec-template.md`
- Enforcement: A doc-lint script (added with Spec 001) walks `docs/specs/*/spec.md` and asserts the section exists and references valid CON-N IDs.

## Process for changing the constitution

1. Add or change an ADR.
2. In the same PR, update this file (`docs/constitution.md`) to reference the ADR and adjust enforcement.
3. If a rule is removed, search `docs/specs/` for references and update those specs in the same PR.
4. CI's `make verify` includes the doc-lint script; constitution drift fails the build.

## Rules that aren't here yet (follow-ups)

- ADR 0003 and ADR 0005 are missing from `docs/adr/`. Either backfill them or renumber 0004/0006/0007/0008 to be contiguous. Not a v0.1 blocker.
- Rule for operator-identity bootstrapping (Ed25519 keypair lifecycle, key rotation, revocation). Will land with Spec 003.
- Rule for the `HypervisorBackend` interface contract (shape of `open / scope / dispatch / close / erase / attest` hooks). Will land with v0.2.
