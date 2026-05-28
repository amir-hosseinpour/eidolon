# Eidolon, agent orchestration

Status: Draft
Last updated: 2026-04-20

## Model

Eidolon uses Claude Code subagents on the operator's laptop as the primary orchestration surface. Per VM FastAPI job servers are the tool edges. Claude Code subagents call the orchestrator. The orchestrator validates scope and dispatches to the VM side server over mTLS.

This lines up with the PentestGPT three module pattern (reasoning, generation, parsing) and the CAI framework's kill chain taxonomy, built on Claude Code's native subagent primitive instead of a custom runner.

## Why Claude Code subagents (and not CrewAI or AutoGen)

Session isolation. Each subagent runs in its own context window. A `recon-agent` does not see `cracker-agent` history. That matches how you actually want pentest tasks scoped.

Native in Claude Code. No separate runtime. Install Eidolon's subagent definitions and they show up as `/agent` invocations.

Cheaper than forking CAI. CAI (Anthropic forks at 8.1k stars) is excellent but is its own runner. Eidolon targets operators who already live in Claude Code.

Respects Consumer Terms 3.7. Claude Code on a personal subscription is interactive dev. Subagents run when the operator invokes them in session, not on a schedule, not as a cron. That's the line we do not cross.

We borrow patterns from CAI (kill chain step naming, SSHTunnel tool shape, scope token plumbing) without the runtime dep. See [ADR 0007](../adr/0007-fork-cai-patterns.md).

## Subagent definitions

Each subagent is a markdown file in `orchestrator/agents/` that Claude Code loads. Canonical shape:

```markdown
---
name: cracker-agent
description: GPU backed hash cracking via CrackQ. Handles NTLM, NTLMv2, WPA, LUKS, bcrypt, sha-crypt. Invokes hashcat on the cracker VM.
tools: [crack_hashes, identify_hash_type, estimate_runtime, import_wordlist]
scope_requires: cracker
---

# Cracker Agent

You are the cracker subagent. You accept a pile of hashes or an archive and decide:

1. Hash type (use `identify_hash_type`).
2. Attack plan (dict + rules, then hybrid, then mask). Estimate runtime first.
3. Submit via `crack_hashes`. Poll to completion. Emit cracked pairs to the session workspace.

## Rules

- Never accept hashes not referenced in the current session's scope.
- If identify_hash_type returns low confidence, ask the operator to confirm.
- If estimated runtime > 24h, require operator confirmation before submit (gate: confirm).

## In scope tools

- crack_hashes(hashes, mode, wordlist, rules, mask) returns job_id
- identify_hash_type(sample) returns {type, confidence}
- estimate_runtime(job_spec) returns duration
- import_wordlist(path, session_id) returns wordlist_id
```

### v0.1 subagents

| Name | VM | Purpose |
|------|-----|---------|
| `cracker-agent` | cracker | Hash cracking |
| `recon-agent` | recon | Active scanning, web testing |
| `analyst-agent` | llm-analyst (via LiteLLM) | Reasoning, summarization, and draft writeups. Routes to commercial or local models depending on session egress policy. |
| `sandbox-agent` | sandbox | Notes, artifacts, draft writing |
| `report-agent` | orchestrator | Findings assembly and summarization |

### v0.2 subagents

| Name | VM | Purpose |
|------|-----|---------|
| `listener-agent` | listener | Sliver implant management |
| `sim-agent` | target-sim | Lab provisioning for training or dry run |
| `tooling-agent` | tooling | Interactive Kali escape hatch |

## Tool plumbing

### Subagent to orchestrator

Every tool call from a subagent is an HTTPS request to `https://eidolon-orchestrator.local/v1/tools/<tool_name>` over WireGuard plus mTLS.

Request body includes:

- `session_id`
- `scope_token` (HMAC SHA256, signed by the operator key, carries session ID, allowed action set, and expiry)
- `action_args`

Orchestrator validates:

- HMAC signature
- Session exists and is not closed
- Requested action is in the allowed action set
- Action's command tier is authorized (autonomous, confirm, prohibited)

If valid, the orchestrator dispatches to the target VM's FastAPI server.

### Orchestrator to VM

Internal mTLS on the `mgmt` VNET.

Each VM runs a FastAPI job server that only exposes tools scoped to its agent.

The VM server re validates the scope token HMAC. Defense in depth.

## Command tier gating

Every tool is labeled with one tier in its definition.

| Tier | Behavior |
|------|----------|
| `autonomous` | Subagent executes, no prompt. |
| `confirm` | Orchestrator prompts the operator in Claude Code. Executes on yes. |
| `prohibited` | Orchestrator refuses. Reserved for things that need out of band auth (for example, prod environment). |

Examples:

- `nmap -sS`. Autonomous.
- `nmap -sS --max-rate 100000` against a /16. Confirm (aggression heuristic).
- Any action against an out of scope CIDR. Prohibited.
- `hashcat` attack. Autonomous.
- `hashcat` attack estimated > 24h. Confirm.
- Any write outside the active session workspace. Prohibited.

Tier gets evaluated at the orchestrator. That's the source of truth, not the subagent prompt.

## PentestGPT three module mapping

| PentestGPT module | Eidolon equivalent |
|-------------------|-------------------|
| Reasoning Session | `analyst-agent` (commercial or local model via LiteLLM, chosen per session egress policy) |
| Generation Session | Claude Code main session on the operator's laptop |
| Parsing Session | Orchestrator's structured output validators plus a small local model for log summarization |

Session isolation is a security property, not just a UX one. Leaking context from the reasoning session into the parsing session is how a prompt injection becomes a scope violation.

## Non Eidolon orchestrators (Paperclip)

The v2.0 Paperclip orchestrator is not a Claude Code subagent. It is a separate runtime (see [`../future/paperclip-orchestrator.md`](../future/paperclip-orchestrator.md)) with a pluggable LLM backend. When Paperclip runs, Claude Code stays the operator's interactive surface. Paperclip handles autonomous tasks between operator sessions.

## Fork and firm customization

downstream forks ('s fork) overrides only the subagent YAML and tool definitions. The orchestrator schema is stable. A firm can:

- Rename agents
- Add tools (firm specific wordlists, internal CTI feeds)
- Tighten gate tiers (force `confirm` for everything by default)
- Swap model router targets
- Layer engagement memory, multi engagement concurrency, client isolation on top

Eidolon does not ship any of those firm grade features. The fork adds them. See [ADR 0001](../adr/0001-fork-from-homelab-blueprint.md) for fork expectations.
