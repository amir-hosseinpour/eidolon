# Spec: Hybrid LLM router with redaction

Feature ID: 005-llm-router-redaction
Status: Draft
Created: 2026-05-28
Updated: 2026-05-28
Spec author: Amir Hosseinpour
Implementation owner: Amir Hosseinpour

## Problem statement

v0.1 already binds every tool call to a scope token (Spec 001), three-tier command gate (Spec 003), and hash-chained audit (Spec 004). The remaining v0.1 governance gap is **runtime LLM calls**: orchestrator code calls a commercial provider directly, bypassing redaction, and there is no single chokepoint where sensitivity classification + audit attach. CON-3 already requires a single router, but no router exists.

This spec wires the LiteLLM router and the redaction pipeline. Every runtime LLM call goes through one endpoint. The endpoint either (a) routes to a commercial provider after a three-pass redaction pass with rehydration on the return trip, or (b) routes to a local model with no redaction when the session declares `strict-local` egress. The router emits one audit event per call. The redaction pipeline lifts the engagement-studio proxy design (deterministic glossary → Presidio analyzer → small local LLM residual flag, no auto-replace) and ships it as `eidolon/orchestrator/lib/redaction/`.

What v0.1 defers:
- Auto-replace from the residual-flag LLM pass. v0.1 flags only, requires human review before egress.
- Per-segment KMS-backed token-map keys (engagement key is good enough for v0.1).
- Streaming. v0.1 routes non-stream completions only; streaming lands in v0.2.
- Provider failover. v0.1 is one commercial + one local. Failover/cascade lands in v0.2.
- Per-call cost dashboards. v0.1 logs cost per call to the audit chain; aggregation UI is downstream.

## User stories

- US-1. As an operator, I want every LLM call my agent makes to route through one endpoint so I can audit, redact, and rate-limit at a single chokepoint.
- US-2. As an operator running an `allow-egress` engagement, I want client identifiers (names, domains, emails, IPs, contact people) redacted before any prompt leaves the host, and rehydrated transparently on the return trip, so I never leak client data to a commercial provider.
- US-3. As an operator running a `strict-local` engagement, I want the router to refuse any call that would touch a commercial provider, and fail loud rather than fall back silently, so I cannot accidentally exfiltrate scope-restricted data.
- US-4. As an auditor, I want one audit entry per LLM call recording: engagement_id, provider, model, prompt_hash, redaction_pass_results, response_hash, latency_ms, token counts, and cost, so I can prove what the AI was asked and what it answered.
- US-5. As a developer, I want an A/B test in CI that runs the same fixture through the router with redaction ON and OFF and asserts the final rehydrated output is identical (modulo sampling variance held at `temperature=0`), so a redaction bug cannot ship.
- US-6. As an operator, I want a `--strict-local` global flag on `eidolon engage start` that pins the engagement's egress policy at creation time and cannot be loosened, so policy can't drift mid-engagement.

## Acceptance criteria

### Router

- AC-1. `LLMRouter.complete(engagement_id, model, messages, **kwargs) -> RouterResponse` is the only LLM entry point in the orchestrator. Grep-test in CI asserts no `httpx.AsyncClient(base_url=...openai.com|gemini|googleapis|anthropic)` outside `eidolon/orchestrator/lib/llm_router.py` (extends CON-3 enforcement to a hard CI gate).
- AC-2. The router reads the engagement's egress policy from the engagement record (set at `engage start`). `allow-egress` → redaction pipeline → commercial provider → rehydration. `strict-local` → local provider, redaction skipped, no commercial provider lookup performed.
- AC-3. `strict-local` failure mode is loud: if the requested `model` resolves to a commercial provider in the LiteLLM config, the router returns `RouterError(reason="strict_local_violation")` and emits an audit event `llm_strict_local_blocked`. No fallback to a local model. The agent must explicitly request a local model id.
- AC-4. Provider routing config lives in `eidolon/orchestrator/conf/litellm.yaml`. Default v0.1 ships: one commercial provider (Gemini 1.5 Pro), one local OpenAI-compatible endpoint (configurable URL). Adding more providers is a config edit, not a code change.
- AC-5. `RouterResponse` carries: `content`, `provider`, `model`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `latency_ms`, `redaction_summary` (counts per category, never raw values), `audit_seq`.

### Redaction

- AC-6. `Redactor.redact(engagement_id, text) -> (redacted_text, TokenMap)` runs three passes in order: (1) per-engagement glossary, (2) Presidio analyzer (entities: `EMAIL_ADDRESS`, `PHONE_NUMBER`, `IP_ADDRESS`, `URL`, `PERSON`, `US_SSN`, `CREDIT_CARD`, `IBAN_CODE`, `LOCATION`, plus a custom `CAN_POSTAL` recognizer), (3) residual-flag LLM pass against a local model.
- AC-7. Pass 3 is **flag-only in v0.1**. Flagged residuals are returned in `RedactionResult.flags` and the router refuses to send the message if any high-confidence flags are present, returning `RouterError(reason="residual_identifier_flagged", flags=[...])`. The operator's Claude Code session displays the flags and prompts for an explicit override (manual edit + retry) or a glossary update + retry.
- AC-8. Token format is `{{CATEGORY_N}}` where `CATEGORY` is the entity type (uppercased, underscore-joined) and `N` is a 1-indexed per-category counter stable within one redaction pass. The same plaintext value within one pass always maps to the same token.
- AC-9. Token map is written to `$EIDOLON_HOME/engagements/<id>/redaction/<request_id>.enc`, encrypted with libsodium sealed-box using a per-engagement symmetric key derived at `engage start` from the engagement's master secret. The token map never leaves the orchestrator host. It is loaded only during rehydration for the matching `request_id`.
- AC-10. `Redactor.rehydrate(redacted_text, token_map) -> text` does a longest-token-first reverse lookup. After rehydration, a sanity scan for `{{[A-Z_]+(?:_\d+)?}}` must return empty; non-empty means the model emitted an unmapped token (rare, possible if the model hallucinates a token-shaped string), and the router returns `RouterError(reason="rehydration_residual_tokens")` rather than ship garbled output.

### A/B correctness test (the non-negotiable)

- AC-11. `tests/test_router_redaction_roundtrip.py` runs the canonical fixture (engagement-studio's `rismans_fragment.md` + `glossary.json`) through the router twice: once with redaction ON, once with the redaction pipeline bypassed. Both passes pin `temperature=0`. After Claude responds, the test asserts: (a) the rehydrated output equals the no-redaction output byte-for-byte after whitespace normalization; (b) the redacted prompt contains zero plaintext values from the token map; (c) the audit chain has exactly one `llm_complete` entry per call.
- AC-12. The A/B test runs in CI on every PR. Failure blocks merge. Skipping (`pytest.mark.skip`) the A/B test requires a separate `audit-bypass` PR label that triggers a notification.

### Audit + lifecycle

- AC-13. Every router call emits one `llm_complete` audit event with: `engagement_id`, `provider`, `model`, `prompt_sha256`, `response_sha256`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `latency_ms`, `redaction_categories_hit` (e.g., `{"EMAIL_ADDRESS": 2, "PERSON": 3}`). Plaintext prompts and responses are not in the audit chain.
- AC-14. `engage erase` deletes `$EIDOLON_HOME/engagements/<id>/redaction/` along with the rest of the workspace (Spec 002 already covers the dir; this just adds the redaction subtree).
- AC-15. `eidolon engage scope` accepts `--egress allow|strict-local` (default `allow`). Once set, the policy is immutable for the lifetime of the engagement. Re-running `engage scope` with a different egress value returns `409 egress_policy_locked`.

## Out of scope

- Streaming completions (v0.2).
- Provider failover / cascading retries (v0.2).
- Per-call cost aggregation UI (downstream forks ship the dashboard; the audit chain has the raw data).
- Auto-replace from the residual-flag pass (v0.2 once we have data to calibrate confidence).
- KMS-backed per-segment token-map keys (v0.2).
- Redaction of file uploads / images (the operator decides what to attach; the router redacts text only). The `engage start` doc will warn explicitly.
- Cross-engagement glossary sharing (no, by design — each engagement is isolated).

## Constitution gates

- [x] **CON-1** — control plane is the product. Router + redaction are control-plane code; runtime stays in the agent's Claude Code session and the BYO backend.
- [x] **CON-2** — no Anthropic endpoints in the runtime path. AC-1's grep test extends to `anthropic` substring; LiteLLM config rejects any `anthropic/*` model group.
- [x] **CON-3** — every runtime LLM call goes through the LiteLLM router. AC-1 makes this a hard CI gate, replacing the previous "code review only" enforcement.
- [x] **CON-4** — every tool call mediated by scope token. Router accepts a scope token and verifies it before doing any work; redaction is implicit because the engagement id comes from the verified token, not from the request body.
- [ ] **NEW CON-7 — egress policy is set once and is immutable.** Spec adds AC-15 enforcing this. Constitution amendment lands in the same PR as Spec 005 sign-off. Phrasing draft: *"The egress policy of an engagement is set at `engage scope` time and cannot be changed without erasing and reopening the engagement. The router enforces. Code path: `EngagementStore.update_scope` raises `EgressPolicyLocked` if the new scope changes the egress field."*
- [ ] **NEW CON-8 — redaction is mandatory for `allow-egress` LLM calls.** Phrasing draft: *"Any LLM call from an engagement with `egress=allow` must pass through the redaction pipeline. The router enforces. Bypass requires a CI label and emits an audit event."*

## Open questions

- `[NEEDS CLARIFICATION]` Default commercial provider: PRD says "Gemini by default" but earlier roadmap notes mentioned both Gemini 1.5 Pro and 2.5 Pro. v0.1 should pin one. Suggest Gemini 1.5 Pro for cost + stable API.
- `[NEEDS CLARIFICATION]` Local residual-flag model: spec defaults to Gemma 3 4B via Ollama (matches engagement-studio reference impl). Alternative is Foundation Sec 8B (already in v0.1 list). Trade-off: Gemma 3 4B is faster + general; Foundation Sec 8B is offsec-tuned + better at distinguishing tool output from identifiers.
- `[NEEDS CLARIFICATION]` Encryption for token maps: libsodium sealed-box is the engagement-studio choice. Eidolon already uses HMAC for scope tokens (Spec 001) but no encryption library yet. Adding `pynacl` to deps. OK?
- `[NEEDS CLARIFICATION]` Cost field accuracy: cost calculation requires per-model pricing table. LiteLLM ships a pricing dict; we wrap it. If the model is unknown, log `cost_usd=null` rather than fail.
- `[NEEDS CLARIFICATION]` Strict-local for the residual-flag pass: in `strict-local` mode the pass is skipped (no egress, no need). But what if the operator runs `allow-egress` and the local residual-flag model is unreachable? Default: hard-fail with `RouterError(reason="redaction_unavailable")` so we don't accidentally egress with weaker redaction. Confirm.

## References

- ADR `docs/adr/0004-litellm-hybrid-router.md` (provider strategy)
- ADR `docs/adr/0002-no-anthropic-api-runtime.md` (CON-2 origin)
- Spec `docs/specs/001-scope-token-end-to-end/spec.md` (scope token contract)
- Spec `docs/specs/004-audit-log-hash-chain/spec.md` (audit event sink for AC-13)
- Engagement-studio prior art: `redactor.py`, `redaction-strategy.md`, `test_redaction_roundtrip.py`, `test_ab_with_without_proxy.py` (lifted as reference implementation)
- Microsoft Presidio: https://github.com/microsoft/presidio
- LiteLLM: https://github.com/BerriAI/litellm
