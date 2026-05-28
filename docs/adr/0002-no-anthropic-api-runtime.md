# ADR 0002: No Anthropic API in the runtime path

Status: Accepted
Date: 2026-04-18

## Context

Claude is the operator's interactive model of choice. Claude Code on a personal subscription is the daily driver. The temptation is to also wire Claude into the runtime agents (orchestrator, per VM job servers, LiteLLM fallbacks).

Two things make this a bad idea.

1. Consumer subscription. Anthropic Consumer Terms 3.7 prohibits scripted, automated, or sub sharing use. OpenClaw's ban on 2026-04-10 is the precedent. Running cron agents or orchestrator requests against `api.anthropic.com` with the consumer account violates ToS.
2. Commercial API. Technically allowed, but any sensitive dual use cyber workload triggers the Cyber Verification Program (CVP) review path. More friction, and it reintroduces single provider risk.

Neither path fits Eidolon's requirement of no single AI provider dependency at runtime.

## Decision

Anthropic endpoints are not called from any Eidolon VM, the orchestrator, or the LiteLLM router. Claude is the operator's personal Claude Code session only. Period.

Runtime agents go through LiteLLM, which fronts:

- Gemini (commercial, for planning and reports)
- Local models served by llama.cpp on the LLM Analyst VM (WhiteRabbitNeo, Foundation Sec 8B, Qwen Coder)

Swapping Gemini for another commercial provider is a one line config change. Swapping in Anthropic's commercial API later, if Eidolon's CVP stance changes, is also a one line change. But not today.

## Consequences

Good:

- Clean ToS posture with the consumer subscription. Operator's interactive Claude Code session stays well inside the terms.
- No single vendor lock in at the runtime layer. If Gemini's terms or pricing change mid engagement, the router swaps without touching agent code.
- Sessions that disallow egress entirely (air gapped labs, sensitive client SOWs) run fully on local models with no code change.

Bad:

- Operators lose the "just use Claude for everything at runtime" convenience. The operator's interactive Claude Code session still gets Claude; everything agentic goes through LiteLLM.
- Local model quality on complex reasoning tasks is lower than frontier commercial. Hybrid routing plus the option to bring in commercial Anthropic through a firm level agreement is the mitigation.
- Extra moving part (LiteLLM) in the runtime path. Standard OpenAI compatible endpoint, so the blast radius is small.

## Alternatives considered

Use the commercial Anthropic API for runtime. Rejected. Single vendor dependency. CVP friction. Breaks the "swappable LLM" invariant.

Use Claude on the consumer sub for runtime. Rejected. Violates Consumer Terms 3.7. OpenClaw's ban is clear precedent.

Run only local models. Rejected for v0.1. Planning and long context tasks (proposals, reports) still benefit from a high end commercial model. Gemini gives us that without requiring Anthropic.
