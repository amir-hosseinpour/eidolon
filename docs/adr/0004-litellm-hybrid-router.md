# ADR 0004: LiteLLM hybrid router (commercial plus local)

Status: Accepted
Date: 2026-04-18

## Context

Eidolon needs an LLM router that can:

- Route by model alias, not vendor name, so code stays provider agnostic.
- Mix commercial and local endpoints.
- Track cost and usage per session for the operator's own accounting.
- Handle retries and fallbacks cleanly.
- Run on prem, no SaaS.

Candidate runtimes: LiteLLM, OpenRouter (SaaS, off limits), Portkey, a hand rolled router.

## Decision

Use LiteLLM as a local sidecar. One OpenAI compatible endpoint for all runtime agents.

Configured model aliases in v0.1:

- `planner` to `gemini/gemini-2.5-pro` (commercial)
- `planner-fast` to `gemini/gemini-2.5-flash` (commercial)
- `offensive` to `local/whiterabbitneo-2.5-7b`
- `sec-qa` to `local/foundation-sec-8b`
- `coder` to `local/qwen2.5-coder-14b`

Local models served by llama.cpp on the LLM Analyst VM, OpenAI compatible HTTP.

Cost tracking in Postgres. Per session tagging via a custom header set by the orchestrator. Langfuse integration comes in v0.2 for full tracing.

## Consequences

Good:

- Single endpoint for all agents.
- Provider swap is a one line YAML edit.
- Cost per session is trivial to surface. Forks can ingest this into their own billing or reporting pipelines.
- LiteLLM already handles retries, fallbacks, rate limits, API key rotation.

Bad:

- Operating an extra service. LiteLLM runs as a sidecar container. Mitigation: simple Docker compose in v0.1. Ship a systemd unit in v1.0.
- LiteLLM itself becomes a dependency. Mitigation: the config is plain YAML. Worst case, we swap LiteLLM for another router with the same schema.

## Alternatives considered

Hand rolled router. Rejected. Reinvents retry, fallback, cost tracking, key rotation. Not our value add.

OpenRouter SaaS. Rejected. Eidolon is on prem, no SaaS runtime. Forks with firm grade data handling concerns (downstream forks) also cannot route data through an unapproved third party.

Portkey. Rejected. Less mature OpenAI compatible endpoint, smaller ecosystem, more SaaS leaning.

Direct vendor SDKs. Rejected. Wedges agent code to a specific provider. Violates ADR 0002 and the portability NFR.
