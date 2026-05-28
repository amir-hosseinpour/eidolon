# DefCon Toronto 2026, talk outline

Status: Draft
Event: DefCon Toronto, May 2026
Talk title (working): Local AI driven offensive security: building a pentest and research environment on commodity hardware
Speaker: Damion (White Tuque)
Length: 40 minutes talk, 10 minutes Q&A

## One line pitch

Self hosted, open source framework for offensive security. One Proxmox box, AI agents on a laptop, no SaaS, no vendor lock in. v0.1 ships with the talk.

## Who this talk is for

Independent pentesters and security researchers who live in Kali, hashcat, and a pile of disconnected tools, and who are tired of AI agent demos that run in one docker container with no scope enforcement.

Not for enterprise buyers. Not for compliance auditors. Not for CISOs. (That audience would be the Voyageur talk, which is not this one.)

## The problem

Three problems, stacked:

1. Pentest tooling is a patchwork. Hashcat on one box, Burp on another, recon in a terminal, notes in Obsidian. Context dies between phases.

2. AI agents for offensive security are early, unsafe, or SaaS only. PentestGPT, PentAGI, CAI run in one container, treat the host as a blob, have no scope enforcement. Pentera and Horizon3.ai solve it behind closed SaaS at thirty to fifty thousand a year.

3. Independent pentesters and researchers want to hack on their own tools. No one is shipping a self hosted, open source, hackable alternative.

## The solution (Eidolon)

One Proxmox box. Role specialized VMs. Each VM owns one phase of the kill chain.

- Cracker VM: GPU hashcat plus CrackQ
- Recon VM: Kali, nmap, nuclei, burp, MCP bridge
- LLM Analyst VM: llama.cpp serving local models (WhiteRabbitNeo, Foundation Sec 8B) for sessions that disallow egress, or as a vendor independent fallback
- Sandbox VM: scratch workspace per session
- Logger VM: append only audit trail

AI agents run on the operator's laptop as Claude Code subagents. Each subagent is scoped to one VM. Every tool call carries a scope token. Three tier command gating: autonomous, confirm, prohibited.

LiteLLM routes model calls. Gemini (or any OpenAI compatible commercial endpoint) by default. Local models when the session disallows egress. No commercial Anthropic in the runtime path for v0.1 (see ADR 0002).

MIT licensed. Fork it, add your firm's compliance and intake layer on top (that is what Voyageur does for White Tuque). Open source framework, proprietary firm overlay.

## Talk structure

### Act 1: The current state (8 minutes)

- Demo the pain: context switching across five tools for one recon phase
- Show three existing AI pentest agents and where they break
- The SaaS commercial alternatives and why indies cannot use them

### Act 2: Design decisions (10 minutes)

- Why Proxmox and not Kubernetes (single node, one operator, no cloud)
- Why role specialized VMs and not one big Kali box (blast radius, scope enforcement, GPU passthrough)
- Why Claude Code subagents and not CrewAI or AutoGen (session isolation, already lives where pentesters already work)
- Why LiteLLM and not direct vendor SDKs (model agnostic by policy, swap providers without touching agent code)
- Why no Anthropic at runtime (Consumer Terms 3.7, stay compliant with the sub the operator is already paying for)

### Act 3: Live demo (15 minutes)

See [`defcon-toronto-2026-demo-plan.md`](./defcon-toronto-2026-demo-plan.md) for the full demo script.

Goal: full kill chain (recon, crack, analyst summary) against a GOAD target, end to end, in under 10 minutes, live, without breaking.

### Act 4: What is next (5 minutes)

- v0.1 ships today (public repo, MIT)
- v0.2 roadmap: scope token HMAC enforcement at every boundary, command tier gating, target sim VM, listener VM
- v1.0 targets: Ansible installer, security audit, operator handbook
- v2.0 Paperclip research: autonomous agent loops with human gates

Hand off to Voyageur framing:

- Eidolon is the framework. It runs one session at a time, no client isolation, no compliance mappings, no engagement memory.
- Firms that need those features build overlays. Voyageur is one example. Public at a high level, private in detail.

### Act 5: Q&A (10 minutes)

Anticipated questions:

- Why not just use Metasploit Pro or Cobalt Strike? (Different problem space. Those are exploitation frameworks, not orchestration frameworks.)
- What AI safety work have you done? (Scope tokens, command tier gating, per VM egress filters, redaction layer, human confirm gates. Not solved. Ongoing research.)
- Can I run this against real clients? (Eidolon itself, no. You need client isolation, compliance, engagement memory. Fork it and build those on top. Voyageur is one way.)
- How is this different from CAI? (CAI is a standalone runtime. Eidolon borrows CAI's patterns without the runtime dep. Ships as Claude Code subagents.)
- How is this different from PentestGPT? (PentestGPT is one container. Eidolon is a full Proxmox host with per VM scope enforcement.)
- Does it work with local NVIDIA? (Yes. CUDA build of llama.cpp. Swap the ROCm build out, same config.)
- Can I use Ollama instead of llama.cpp? (Yes. OpenAI compatible endpoint is the only requirement.)

## Pre talk deliverables

See [`release-v0.1-checklist.md`](../release-v0.1-checklist.md).

## Slide deck (TBD)

Build on top of the Voyageur executive presentation as a base. Strip Voyageur specific content. Focus on framework, operator, AI agent, scope enforcement. Add live demo slide slots.

## Leave with

- Public repo URL
- Discord / matrix / irc for community
- Link to docs/architecture/overview.md
- Link to docs/presentations/defcon-toronto-2026-demo-plan.md if anyone wants to reproduce the demo
