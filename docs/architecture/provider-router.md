# Eidolon, provider router (LiteLLM)

Status: Draft
Last updated: 2026-04-18

## Goal

Treat "LLM" as a commodity you can swap. No Eidolon runtime path should be wedged to a single provider.

## What not to do

Do not call `api.anthropic.com` from the orchestrator or any VM. Not with the consumer account, and not with a credit provisioned API key you happen to have.

Consumer Claude subscription means interactive Claude Code on the operator's laptop. That's it. Anthropic Consumer Terms 3.7 prohibits scripted or automated or sub sharing use. OpenClaw's ban on 2026-04-10 is the precedent.

Commercial Anthropic API is fine technically, but it reintroduces single provider dependency. For sensitive dual use cyber work it also triggers the CVP (Cyber Verification Program) review path. That's extra friction we don't need.

See [ADR 0002](../adr/0002-no-anthropic-api-runtime.md).

## Architecture

```
┌─────────────────────────────────┐
│     Orchestrator / Agents       │
└────────────────┬────────────────┘
                 │ OpenAI-compat HTTP
                 ▼
┌─────────────────────────────────┐
│     LiteLLM Router (sidecar)    │
│  - API-key auth                 │
│  - Cost / usage tracking        │
│  - Rate limiting                │
│  - Retry + fallback chains      │
└────────────┬────────┬───────────┘
             │        │
      ┌──────┘        └──────────┐
      ▼                          ▼
┌─────────────┐       ┌──────────────────────┐
│ Gemini API  │       │   LLM-Analyst VM     │
│ (2.5 Pro,   │       │   - llama.cpp server │
│  Flash)     │       │   - WhiteRabbitNeo   │
│             │       │   - Foundation-Sec-8B│
│             │       │   - Qwen2.5-Coder    │
└─────────────┘       └──────────────────────┘
```

## Configured models (v0.1)

| Alias | Backing | Tier | Used for |
|-------|---------|------|----------|
| `planner` | `gemini/gemini-2.5-pro` | commercial | High context planning, report generation, vision (screenshots of burp traces) |
| `planner-fast` | `gemini/gemini-2.5-flash` | commercial | Routine reasoning |
| `no-egress` | `local/whiterabbitneo-2.5-7b` | local | Offensive reasoning for sessions that forbid egress |
| `sec-qa` | `local/foundation-sec-8b` | local | Security QA, CVE and protocol lookup |
| `coder` | `local/qwen2.5-coder-14b` | local | Tool calling, code generation, bash |

Aliases are semantic. Orchestrator code references `planner`, not `gemini-2.5-pro`.

## Routing rules

LiteLLM config lives at `orchestrator/litellm-config/config.yaml`.

```yaml
model_list:
  - model_name: planner
    litellm_params:
      model: gemini/gemini-2.5-pro
      api_key: os.environ/GEMINI_API_KEY
  - model_name: planner-fast
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
  - model_name: no-egress
    litellm_params:
      model: openai/whiterabbitneo-2.5-7b
      api_base: http://llm-analyst.eidolon.local:8080/v1
      api_key: local-no-auth
  - model_name: sec-qa
    litellm_params:
      model: openai/foundation-sec-8b
      api_base: http://llm-analyst.eidolon.local:8080/v1
      api_key: local-no-auth
  - model_name: coder
    litellm_params:
      model: openai/qwen2.5-coder-14b
      api_base: http://llm-analyst.eidolon.local:8080/v1
      api_key: local-no-auth

router_settings:
  routing_strategy: simple-shuffle
  fallbacks:
    - { planner: [planner-fast, coder] }
    - { no-egress: [sec-qa] }

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/LITELLM_DB_URL   # Postgres for cost tracking
```

## Why Gemini for planner (and not the obvious choices)

Neutral on Anthropic independence (the primary constraint).

Long context (2M tokens) fits multi target session plans.

Vision in the same model, cheap. Screenshot analysis works.

Google Cloud billing is acceptable to most clients.

Pairing with local models is not about bypassing refusals. It is about covering the case where a session disallows egress entirely, and giving operators a vendor independent fallback if a commercial provider's terms change mid engagement.

For firms that can't send data to Google, the router config is literally one `model:` line per model. Swap in OpenAI `o*`, Mistral, DeepSeek R1, or commercial Anthropic with a firm level agreement. Nothing else changes.

## Local models, why these

Local models cover two jobs: egress-denied sessions, and vendor-independent fallback. They are not the "offensive" tier. They are the "on prem only" tier.

WhiteRabbitNeo 2.5 7B. Security tuned, runs comfortably on modest GPU, sized for a single node lab. Default pick when a session runs with egress disabled.

Foundation Sec 8B (Cisco). Tuned on real CVE, pentest, and incident response corpora. Good at "what is this protocol, is this MSRPC enum, what's the CVE for this banner?"

Qwen 2.5 Coder 14B. Best tool calling in a size that runs on 16 GB VRAM at reasonable quant. Used for glue prompts (convert this nmap output to JSON with fields X/Y/Z), regardless of egress policy, because there is no reason to spend commercial tokens on plumbing.

Once an RTX PRO 6000 is available, upgrade to `Llama-3.3-70B-Instruct` or a 70B tune, so the no egress path is closer in quality to the commercial path.

## Budget and observability

LiteLLM writes per request usage to Postgres:

- Model
- Tokens in/out
- Cost (local = 0, except for GPU hour accounting)
- Session ID (via a custom header set by the orchestrator)

Daily cron generates the per session cost report, stored in the session workspace.

Langfuse integration (v0.2) for full tracing and quality review.

## What the operator's Claude Code does not do

Does not proxy to LiteLLM.

Does not share session data with VMs.

Tool calls to VMs go out through `eidolon` CLI to orchestrator to LiteLLM, fully isolated from the operator's Claude Code session.

That's the wedge that keeps the consumer Claude sub inside ToS. Claude is the operator's interactive co pilot. Everything agentic runs server side, model agnostic, on providers whose terms allow it.
