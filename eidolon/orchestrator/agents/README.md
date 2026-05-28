# Eidolon subagents

Each subagent is a Claude Code style markdown card. The orchestrator loads these
at session start, exposes them to the operator, and enforces scope and tier
gating before any tool call leaves the host.

Default roster:

- `recon-agent.md` — passive and active recon inside scope CIDRs
- `cracker-agent.md` — offline hash cracking on the GPU node
- `analyst-agent.md` — summarize findings, propose next steps
- `sandbox-agent.md` — ad hoc scratch work inside the sandbox VM
- `report-agent.md` — draft findings from signed log extracts

Eidolon subagents run one session at a time. Firm grade multi engagement
orchestration and engagement memory tooling live in downstream forks.
