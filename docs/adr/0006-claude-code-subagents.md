# ADR 0006: Claude Code subagents as the operator surface

Status: Accepted
Date: 2026-04-18

## Context

The operator needs a way to drive per VM workflows from a single interface. Options:

- A custom runner (CAI, CrewAI, AutoGen). Own the UX end to end, but add another runtime.
- Claude Code subagents. Native in Claude Code, session isolated by default, no extra runtime on the laptop.
- A web UI. Consistent with a SaaS product. Not Eidolon.

We also want to stay inside Anthropic Consumer Terms 3.7. Subagents run when the operator invokes them in session. They are not cron jobs. They are not an automation proxy. That distinction matters.

## Decision

Claude Code subagents are the primary operator orchestration surface.

Each VM role has a subagent definition in `orchestrator/agents/` (markdown with a YAML frontmatter). Tools scoped per agent. Gate tier per tool. Scope token enforced at the orchestrator.

Heavy lifting still runs on the server: orchestrator validates scope, dispatches to the VM's FastAPI job server, streams results back.

Paperclip (v2.0) is a different runtime for autonomous ops. It is not a Claude Code subagent.

## Consequences

Good:

- No separate runtime on the laptop. Operator already has Claude Code.
- Native session isolation. `recon-agent` does not see `cracker-agent` history.
- Clean ToS posture. The operator invokes the subagent in their interactive session.
- Firms can fork the subagent YAML without touching the orchestrator schema.

Bad:

- Tied to Claude Code as the operator UI. Operators who prefer another editor cannot use Eidolon interactively until we add a parallel surface. Mitigation: `eidolon` CLI covers the same workflows for non Claude Code users.
- Subagent capability is bounded by what Claude Code exposes. Future Claude Code API changes could force redesign.

## Alternatives considered

CAI as the operator runtime. Rejected. Great patterns, but duplicates what Claude Code already does. We borrow patterns without taking the runtime dep. See ADR 0007.

CrewAI or AutoGen. Rejected. Same reasoning. Also, neither fits naturally on the operator laptop.

Bespoke web UI. Rejected for v0.x. Maybe v1.0 or later. Adds a frontend maintenance load we do not want yet.

CLI only. Rejected. The CLI stays as a fallback. Operators who want to drive multi step agent workflows will want an interactive model, and Claude Code is the best one available today.
