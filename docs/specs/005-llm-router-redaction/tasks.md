# Tasks: Hybrid LLM router with redaction

Spec: `./spec.md`
Plan: `./plan.md`
Status: Draft

Conventions: `[P]` = parallelizable. TDD order — failing tests first, then implementation.

## Tasks

### T-01 [P] Failing tests for `TokenMap` + glossary pass

File: `tests/test_redaction.py` (initial subset)

Tests: `test_token_map_add_assigns_stable_token`, `test_token_map_add_dedupes_same_plaintext_same_category`, `test_token_map_reserve_overrides_counter`, `test_glossary_pass_replaces_longest_first`, `test_glossary_pass_is_case_sensitive_word_boundary`. Must fail before T-05.

### T-02 [P] Failing tests for Presidio pass

File: `tests/test_redaction.py` (extends T-01)

Tests: `test_presidio_pass_redacts_email_phone_ip_url_person`, `test_presidio_pass_skips_inside_existing_tokens`, `test_presidio_pass_custom_can_postal_recognizer`. Skip whole test class if `presidio_analyzer` not installed (signal redaction extra not present). Must fail before T-06.

### T-03 [P] Failing tests for residual-flag pass

File: `tests/test_redaction.py` (extends T-01)

Tests: `test_residual_flag_pass_returns_flags_only_no_substitution`, `test_residual_flag_pass_skipped_when_strict_local`, `test_residual_flag_pass_raises_when_unreachable_in_allow_egress`. Mock the local LLM HTTP call. Must fail before T-07.

### T-04 [P] Failing tests for token-map encryption + persistence

File: `tests/test_redaction.py` (extends T-01)

Tests: `test_token_map_persisted_encrypted`, `test_token_map_round_trip_via_disk`, `test_token_map_dir_under_engagement_workspace`, `test_engage_erase_removes_redaction_dir`. Must fail before T-08.

### T-05 Implement `TokenMap` + glossary pass

File: `eidolon/orchestrator/lib/redaction/token_map.py`, `redactor.py` (glossary section)

Lift from engagement-studio `redactor.py` lines 24–53. Adapt to TokenMap dataclass with `request_id`, `engagement_id`, `created_at`. Make T-01 pass.

### T-06 Implement Presidio pass

File: `eidolon/orchestrator/lib/redaction/presidio_pass.py`

Lift from engagement-studio `redactor.py` lines 59–83. Add custom `CAN_POSTAL` recognizer for Canadian postal codes (regex `\b[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d\b`). Make T-02 pass.

### T-07 Implement residual-flag pass

File: `eidolon/orchestrator/lib/redaction/residual_flag.py`

Adapt from engagement-studio `redactor.py` lines 86–110. Default model: `gemma3:4b` via Ollama-compatible endpoint. Configurable via `EIDOLON_REDACTION_FLAG_URL`. Make T-03 pass.

### T-08 Implement encrypted token-map persistence

File: `eidolon/orchestrator/lib/redaction/token_map.py` (extend)

Use `pynacl` SealedBox with a per-engagement keypair stored in `$EIDOLON_HOME/engagements/<id>/.redaction-key`. Write `<request_id>.enc` to `$EIDOLON_HOME/engagements/<id>/redaction/`. Wire `EngagementStore.erase` to delete the dir (touches Spec 002 erase path). Make T-04 pass.

### T-09 [P] Failing tests for `LLMRouter.complete` happy paths

File: `tests/test_llm_router.py`

Tests: `test_complete_allow_egress_routes_to_commercial_after_redaction`, `test_complete_strict_local_routes_to_local`, `test_complete_redacts_then_rehydrates`, `test_complete_emits_llm_complete_audit_with_hashes`. Use a `FakeLiteLLM` that records calls. Must fail before T-12.

### T-10 [P] Failing tests for `LLMRouter` error modes

File: `tests/test_llm_router.py` (extends T-09)

Tests: `test_strict_local_blocks_commercial_model_with_audit`, `test_residual_flagged_raises_412_and_audits`, `test_rehydration_residual_tokens_raises_500_and_audits`, `test_scope_token_invalid_returns_401`, `test_egress_policy_locked_returns_409_on_scope_change`. Must fail before T-12.

### T-11 [P] Failing test for A/B correctness roundtrip

File: `tests/test_router_redaction_roundtrip.py`

The non-negotiable A/B test (AC-11). Uses `tests/fixtures/redaction/canonical_fragment.md` + `canonical_glossary.json`. Pinned `temperature=0`. Asserts: rehydrated-with-redaction == response-without-redaction (whitespace-normalized), redacted prompt has zero plaintext leakage, one `llm_complete` audit entry per call. Uses `FakeLiteLLM` that mimics a deterministic provider response derived from input message hash. Must fail before T-13.

### T-12 Implement `LLMRouter.complete`

Files: `eidolon/orchestrator/lib/llm_router.py`, `eidolon/orchestrator/conf/litellm.yaml`, `eidolon/orchestrator/lib/litellm_client.py` (thin wrapper)

Implement the flow from `plan.md` "Routing logic". Wire `RouterResponse`, `RouterError`. Pin Gemini 1.5 Pro as the commercial default in config. Make T-09 + T-10 pass.

### T-13 Author A/B fixtures + finalize roundtrip test

Files: `tests/fixtures/redaction/canonical_fragment.md`, `canonical_glossary.json`

Rewrite the engagement-studio Rismans fixture as a generic fictional client (`AcmeCorp` / `acmecorp.io` / `J. Doe`). Make T-11 pass.

### T-14 [P] Failing tests for egress policy lock

File: `tests/test_engagement_egress.py`

Tests: `test_engage_scope_accepts_egress_allow`, `test_engage_scope_accepts_egress_strict_local`, `test_engage_scope_change_egress_raises_409`, `test_engagement_record_has_frozen_egress_after_first_scope`. Must fail before T-15.

### T-15 Implement egress policy on `ScopeDocument` + `Engagement`

Files: `eidolon/orchestrator/lib/scope.py`, `engagements.py`, `app/routers/engagements.py`, `cli/main.py`

Add `egress` to `ScopeDocument` (default `"allow"`). Add `egress_policy` to `Engagement`, set on first scope, locked on subsequent scope calls. CLI: `eidolon engage scope --egress {allow,strict-local}`. Make T-14 pass.

### T-16 [P] CON-3 grep gate in CI

File: `.github/workflows/verify.yml`

Add the step from `plan.md` "Constitution gate hook". Fails the build on a stray `httpx.AsyncClient(base_url=...openai|gemini|googleapis|anthropic)` outside the router.

### T-17 ADR-0009 + constitution amendments

Files: `docs/adr/0009-redaction-mandatory-for-egress.md`, `docs/constitution.md` (append CON-7, CON-8)

ADR captures the egress-lock + mandatory-redaction decision. Constitution adds the two rules with enforcement notes referencing AC-3 + AC-15.

### T-18 [P] Docs: architecture + diagram

Files: `docs/architecture/llm-router.md`, `docs/diagrams/llm-router-pipeline.d2`, `docs/diagrams/llm-router-pipeline.svg`

One-page overview, one sequence diagram showing redact → route → rehydrate with the audit emission point.

### T-19 [P] `pyproject.toml` updates

Add `pynacl`, `litellm`, optional extras group `[redaction]` with `presidio-analyzer`, `spacy>=3.7`, `requests`. Add `[gpu]` reservation for v0.2.

### T-20 README quick-start: add LLM router example

Files: `README.md` (Quick start section)

Show `eidolon engage scope ... --egress allow --permit llm.complete` plus a `claude` MCP example calling the router.

## Sequencing

```
T-01..T-04 (tests in parallel)
   ↓
T-05 → T-06 → T-07 → T-08          (impl, mostly serial)
   ↓
T-09..T-11 (more tests, parallel)
   ↓
T-12 → T-13                         (router + A/B fixtures)
   ↓
T-14 → T-15                         (egress policy)
   ↓
T-16, T-17, T-18, T-19 (parallel polish)
   ↓
T-20                                (README, done)
```

## Estimate

12 hours of focused work. Adjust if Presidio install pain or Gemini API quirks bite.

## Definition of done

- All 20 tasks ticked.
- CI green on PR including A/B test (AC-11) and grep gate (T-16).
- ADR + constitution amendments merged.
- Manual smoke: `eidolon engage start --slug rt-test --egress allow` → invoke router from a fake agent → confirm rehydrated text, audit entry, token-map encrypted on disk.
- Same smoke with `--egress strict-local` and a commercial model id → expect 409.
