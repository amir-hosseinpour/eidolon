# Paperclip orchestrator (future, v2.0)

Status: Research phase. Not planned for v1.0.
Last updated: 2026-04-20

## The idea

Eidolon v0.1 through v1.0 assumes a human operator drives every session from Claude Code. Paperclip is the v2.0 experiment: an autonomous orchestrator that runs between operator reviews.

This is a research surface. Offensive AI agents are early. Eidolon ships the plumbing so researchers can try autonomous loops against safe targets (Target Sim VM, GOAD) without rewriting the orchestrator, scope token, or logging plane.

Firm grade autonomous operation (multi engagement, proposal drafting, client communication, scheduled runs against production client scope) is not in Eidolon. That belongs to forks. downstream forks has its own Paperclip overlay.

## Why the name Paperclip

It borrows the pattern from the operator's personal homelab Paperclip stack, a small task oriented agent runner. The offensive variant is the same pattern, different deployment.

## Hard requirements

Pluggable LLM backend. Can run on local models only. Can run with commercial planner plus local offensive. No hardcoded provider.

Human gates on risk. Every prohibited action is refused at the orchestrator. Every confirm tier action pauses for a human. Autonomous tier actions proceed without asking.

Full audit trail. Same Logger VM, same structured JSON. Paperclip is an actor in the log, named per run.

Reversible where possible. Paperclip prefers dry run first, then execute, then log, then check.

Scope respect. Paperclip cannot exceed the scope token. Same orchestrator level enforcement as a human driven session.

## What it does in Eidolon's scope

Autonomous recon. Paperclip runs nmap, nuclei, subfinder, katana against the session's scope without asking. Results stream to the sandbox workspace. Paperclip summarizes.

Triage and plan drafting. Paperclip reviews recon output, proposes next moves, waits for the human at any confirm tier action.

Tool dispatch with gates. Approved actions execute. Prohibited actions refuse. Confirm tier actions prompt.

Draft summarization. As findings land, Paperclip writes structured notes to the session workspace. The human reads, edits, uses.

## What it does not do in Eidolon

Does not talk to external parties. Eidolon has no concept of a client.

Does not draft proposals, scope documents, or deliverables. That is a firm concern.

Does not coordinate multiple humans on one session. Eidolon is single operator.

Does not handle engagement memory across sessions. Eidolon sessions are isolated.

Does not make exploit decisions that could legally or ethically be contested. Those are confirm tier or prohibited.

## Architecture

```
┌──────────────────────┐
│ Paperclip runner │ (separate VM or orchestrator container)
│ - Task queue │
│ - Agent loop │
│ - Human gate CLI │
└──────────┬───────────┘
 │
 ▼
┌──────────────────────┐
│ Eidolon Orchestrator│ (unchanged from v1.0)
└──────────┬───────────┘
 │
 ┌──────┴─────────┐
 ▼ ▼
[ LiteLLM ] [ VM job servers ]
```

Paperclip is a client of the Eidolon orchestrator, same as Claude Code. It uses scope tokens the same way. It plays by the same rules.

The difference is that Paperclip runs unattended between human review cycles. Claude Code runs with the operator present.

## Pluggable LLM backend

Paperclip's reasoning model is configured at runtime.

Options:

- Local only: `local/llama-3.3-70b` via LiteLLM.
- Hybrid: `planner` (Gemini) for planning, `offensive` (WhiteRabbitNeo) for offensive reasoning.
- Single commercial: `planner` only, for operators with API access but no local GPU.

Model choice is declared per session. Paperclip calls it through the same LiteLLM endpoint the rest of Eidolon uses.

## Human gate UX

Two surfaces:

1. CLI (`paperclip review`): shows pending approvals, one at a time, with context. Human approves, edits, or rejects.
2. Notification channel: optional. Email, Slack, SMS, whatever. Config driven.

Never silent. If Paperclip hits a gate and no human responds, the action waits.

## Safety rails

Token budget per session. Paperclip stops and escalates if it exceeds.

Action budget per window. Paperclip cannot run 10k nuclei scans against one host without a human checkin.

Deadman timer. If the human has not checked in for N hours (operator config), Paperclip pauses autonomous work.

Loop detection. If Paperclip re attempts the same failed action three times, it stops and escalates.

## Why not v1.0

v1.0 is about proving the Eidolon infrastructure (session lifecycle, scope enforcement, audit). Paperclip rides on top of that infrastructure. Trying to build both at once is how you end up with neither working.

Offensive AI agent research is also young. Operators will want to see the v1.0 infrastructure running clean for a while before pointing an autonomous orchestrator at anything that matters.

## Dependencies on v1.0

Scope token HMAC enforced at every boundary.
Three tier command gating working reliably.
Audit trail over rsyslog TLS working.
LiteLLM router stable.
Target Sim VM (v0.2) available for dry runs.

If any of those slips in v1.0, Paperclip cannot ride on top of it in v2.0.

## Open questions

How does Paperclip persist across restarts? State machine in Postgres? Event sourced?

How does Paperclip handle the case where the operator adds scope mid session? A new scope token gets issued, but Paperclip's in flight plans may have assumed the old scope.

What is the test harness for Paperclip? Target Sim VM plus canned scenario scripts?

## Related

- [`../architecture/agent-orchestration.md`](../architecture/agent-orchestration.md) (today's agent model)
- [`../../ROADMAP.md`](../../ROADMAP.md) (v2.0 scheduling)
