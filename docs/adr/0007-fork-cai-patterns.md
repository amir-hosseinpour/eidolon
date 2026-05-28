# ADR 0007: Borrow CAI patterns without the runtime dependency

Status: Accepted
Date: 2026-04-18

## Context

CAI (Alias Robotics, 8.1k GitHub stars) is the leading open source framework for offensive AI agents. It ships:

- A kill chain taxonomy that matches how pentesters actually think.
- An SSHTunnel tool that cleanly separates operator identity from target traffic.
- A scope token pattern for agent permissioning.
- A three session isolation model aligned with PentestGPT.

The temptation is to fork CAI and build on top of it. The concern is that CAI is its own runner with its own config format, lifecycle, and operator UX. Eidolon's target operator already lives in Claude Code (ADR 0006). Adding CAI as a second runtime means two runtimes to maintain for no user benefit.

## Decision

Borrow CAI's patterns. Do not take the runtime dependency.

Specifically:

- Kill chain step naming: Recon, Initial Access, Privilege Escalation, Lateral Movement, Persistence, Collection, Exfil, Impact. Subagents are scoped along these lines where appropriate.
- SSHTunnel tool shape. Eidolon's VM tools follow the same "identity separation" pattern for operator versus target traffic.
- Scope token pattern. HMAC signed, short lived, carries the session ID and allowed action set.
- Session isolation. Each subagent runs in its own Claude Code context window. Mirror of PentestGPT's three module model.

We do not:

- Run CAI as a runtime.
- Depend on CAI's config format.
- Ship CAI as a bundled dep.

Attribution lives in the README and the relevant code comments.

## Consequences

Good:

- Operators get CAI's hard won patterns without another runtime.
- Clean separation: CAI evolves upstream, Eidolon pulls good ideas with a cherry pick.
- No config schema lock in. If CAI refactors tomorrow, Eidolon is unaffected.

Bad:

- Some community familiarity (operators who know CAI) does not transfer directly. Mitigation: document the mapping explicitly in `agent-orchestration.md`.
- We lose the option to pipe CAI specific tools in without porting them.

## Alternatives considered

Fork CAI. Rejected. Two runtimes. Ties Eidolon's release cadence to CAI's.

Depend on CAI as a library. Rejected. Python dep management for offensive tooling is already a headache. Adding CAI compounds it.

Ignore CAI entirely. Rejected. Their patterns are good. Not borrowing them would be ego driven.
