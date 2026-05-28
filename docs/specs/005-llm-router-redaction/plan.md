# Plan: Hybrid LLM router with redaction

Spec: `./spec.md`
Status: Draft
Updated: 2026-05-28

## Architecture

```
eidolon/orchestrator/lib/llm_router.py                  (new)    -> LLMRouter.complete, RouterResponse, RouterError
eidolon/orchestrator/lib/redaction/                     (new pkg)
    __init__.py                                         (new)    -> public surface (Redactor, TokenMap)
    redactor.py                                         (new)    -> three-pass pipeline (lifted from engagement-studio)
    presidio_pass.py                                    (new)    -> Presidio wrapper + custom recognizers
    residual_flag.py                                    (new)    -> Pass 3 local LLM flag (no auto-replace)
    token_map.py                                        (new)    -> TokenMap struct + encrypted persistence
eidolon/orchestrator/lib/engagements.py                 (modify) -> Engagement.egress_policy, egress lock
eidolon/orchestrator/lib/scope.py                       (modify) -> ScopeDocument.egress field
eidolon/orchestrator/app/routers/llm.py                 (new)    -> POST /v1/engagements/<id>/llm/complete
eidolon/orchestrator/app/routers/engagements.py         (modify) -> scope endpoint enforces egress lock
eidolon/orchestrator/conf/litellm.yaml                  (new)    -> provider config (Gemini + local OAI-compat)
eidolon/cli/main.py                                     (modify) -> `engage scope --egress allow|strict-local`
tests/test_llm_router.py                                (new)    -> AC-1..AC-5, AC-13, AC-15
tests/test_redaction.py                                 (new)    -> AC-6..AC-10
tests/test_router_redaction_roundtrip.py                (new)    -> AC-11, AC-12 (the A/B gate)
tests/fixtures/redaction/canonical_fragment.md          (new)    -> generic fixture (rewrite of rismans_fragment.md)
tests/fixtures/redaction/canonical_glossary.json        (new)    -> matching glossary
docs/architecture/llm-router.md                         (new)    -> overview diagram + sequence
docs/diagrams/llm-router-pipeline.d2 + .svg             (new)    -> redact → route → rehydrate
docs/adr/0009-redaction-mandatory-for-egress.md         (new)    -> ADR for CON-7 + CON-8
docs/constitution.md                                    (modify) -> add CON-7, CON-8
pyproject.toml                                          (modify) -> add `presidio-analyzer`, `pynacl`, `litellm` deps
```

## Data model

```python
# In eidolon/orchestrator/lib/redaction/token_map.py

@dataclass
class TokenMap:
    forward: dict[str, str]                # token -> plaintext
    counters: dict[str, int]               # category -> last used n
    request_id: str
    engagement_id: str
    created_at: int                        # unix seconds, UTC

    def add(self, category: str, plaintext: str) -> str: ...
    def reserve(self, token: str, plaintext: str) -> None: ...
    def to_dict(self) -> dict: ...

@dataclass
class RedactionResult:
    redacted_text: str
    token_map: TokenMap
    categories_hit: dict[str, int]         # for audit
    flags: list[str]                       # pass-3 residuals
```

```python
# In eidolon/orchestrator/lib/llm_router.py

class RouterResponse(BaseModel):
    content: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None
    latency_ms: int
    redaction_summary: dict[str, int]
    audit_seq: int

class RouterError(Exception):
    def __init__(self, reason: str, **extra: Any) -> None:
        self.reason = reason
        self.extra = extra
```

```python
# Egress policy on engagement / scope

EgressPolicy = Literal["allow", "strict-local"]

class ScopeDocument(BaseModel):
    allowed_cidrs: list[str]
    allowed_actions: list[str]
    tier: str
    egress: EgressPolicy = "allow"         # new field, default permissive

class Engagement(BaseModel):
    # existing fields...
    egress_policy: EgressPolicy            # frozen at first `engage scope` call
```

## Routing logic

```python
async def complete(
    self,
    *,
    engagement_id: str,
    scope_token: str,
    model: str,
    messages: list[dict],
    **kwargs: Any,
) -> RouterResponse:
    self._verify_scope_or_403(scope_token, engagement_id)
    eng = self._store.get(engagement_id)
    provider = self._litellm.resolve_provider(model)

    if eng.egress_policy == "strict-local" and provider.is_commercial:
        self._audit("llm_strict_local_blocked", model=model, provider=provider.name)
        raise RouterError(reason="strict_local_violation")

    if eng.egress_policy == "allow" and provider.is_commercial:
        result = self._redactor.redact(engagement_id, _flatten(messages))
        if result.flags:
            self._audit("llm_residual_flagged", flags=result.flags)
            raise RouterError(reason="residual_identifier_flagged", flags=result.flags)
        redacted_messages = _rebuild(messages, result)
        self._token_store.put(result.token_map)        # encrypted at rest
    else:
        redacted_messages = messages
        result = None

    started = monotonic_ns()
    raw = await self._litellm.complete(model=model, messages=redacted_messages, **kwargs)
    latency_ms = (monotonic_ns() - started) // 1_000_000

    content = raw.choices[0].message.content
    if result is not None:
        content = self._redactor.rehydrate(content, result.token_map)
        # AC-10 sanity: rehydrate raises RehydrationResidualError if {{...}} left over

    audit_seq = self._audit(
        "llm_complete",
        provider=provider.name,
        model=model,
        prompt_sha256=sha256(_flatten(messages)),
        response_sha256=sha256(content),
        prompt_tokens=raw.usage.prompt_tokens,
        completion_tokens=raw.usage.completion_tokens,
        cost_usd=self._cost(raw, model),
        latency_ms=latency_ms,
        redaction_categories_hit=(result.categories_hit if result else {}),
    )
    return RouterResponse(...)
```

## REST surface

```
POST /v1/engagements/{eng_id}/llm/complete
Headers: Authorization: Bearer <orchestrator_token>
         X-Eidolon-Scope-Token: <scope_token>
Body:
  {
    "model": "gemini-1.5-pro",
    "messages": [...],
    "temperature": 0.0
  }
Responses:
  200 OK -> RouterResponse JSON
  401 -> scope_token_invalid
  403 -> tier_too_low | scope_mismatch
  409 -> strict_local_violation | egress_policy_locked
  412 -> residual_identifier_flagged   (body: {flags: [...]})
  503 -> provider_unreachable | redaction_unavailable
```

## Constitution gate hook

CI step (new) in `.github/workflows/verify.yml`:

```yaml
- name: CON-3 chokepoint check
  run: |
    ! grep -rE "httpx\.AsyncClient\(.*?base_url=.*(openai|gemini|googleapis|anthropic)" \
        eidolon/ \
        --include='*.py' \
        --exclude-dir=__pycache__ \
        --exclude='eidolon/orchestrator/lib/llm_router.py' \
        --exclude='eidolon/orchestrator/lib/litellm_client.py'
```

Fails the build if any module other than the router instantiates a commercial HTTP client.

## Open implementation questions (resolve before T-01)

1. **Presidio model size**: spaCy `en_core_web_sm` is 50 MB; `en_core_web_lg` is 600 MB. Default to `sm`; document `lg` as opt-in.
2. **Glossary source of truth**: per-engagement glossary lives where? Proposed: `$EIDOLON_HOME/engagements/<id>/glossary.json`, written by `eidolon engage glossary add KEY VALUE` (new CLI verb, also in this spec).
3. **LiteLLM as a library vs proxy**: PRD says "LiteLLM proxy" but for v0.1 the orchestrator is single-host. Use LiteLLM as a Python library; document the proxy mode as v0.2.
4. **temperature pinning for the A/B test**: set in fixture, not enforced globally. Other calls can use whatever temperature the agent picks.

## Risks

- **R-1.** Presidio + spaCy add ~200 MB to install. Mitigation: optional extras (`pip install -e ".[redaction]"`), document that egress mode requires the extra.
- **R-2.** Local residual-flag LLM unavailable. Mitigation: AC's hard-fail behaviour for allow-egress sessions; for strict-local sessions the pass is skipped anyway.
- **R-3.** Token map encryption key derivation: deriving from engagement master secret means losing the master loses redaction history. Acceptable for v0.1; v0.2 considers KMS.
- **R-4.** A/B test flakiness: even `temperature=0` is not bit-exact across some providers. Use whitespace-normalized text equality, not byte equality. Spec AC-11 already says this.
