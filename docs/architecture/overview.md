# Eidolon, architecture overview

Status: Draft, v0.1 target
Last updated: 2026-04-20

## One paragraph summary

Eidolon is a self hosted, open source framework for offensive security work. A single operator drives sessions from a laptop running Claude Code. Heavy or specialized work runs on a Proxmox host as role specialized VMs. Model routing goes through LiteLLM, which fronts a commercial provider (Google Gemini by default, swap in OpenAI or Anthropic through a firm level agreement) for sessions that allow egress, and local models (WhiteRabbitNeo, Foundation Sec 8B, Qwen Coder) served by llama.cpp on an AMD GPU for sessions that do not. Anthropic's consumer Claude sub is used only for the operator's interactive Claude Code session, never at runtime inside a VM. That keeps us inside Consumer Terms 3.7.

Eidolon does not ship client isolation, compliance artifacts, multi session concurrency, or engagement memory. Those are firm concerns, carried by forks like Voyageur.

![Architecture overview](../diagrams/architecture-overview.svg)

## Topology

```
┌───────────────────────────────┐
│   Operator Workstation (Mac)  │
│   - Claude Code (consumer)    │
│   - eidolon CLI                │
│   - WireGuard to host         │
└──────────────┬────────────────┘
               │ mTLS + scope token
               ▼
┌───────────────────────────────────────────────────────────────┐
│                    Proxmox VE 8+ Host                         │
│                                                               │
│  ┌──────────────────┐    ┌──────────────────────────────┐     │
│  │ Orchestrator VM  │◄──►│       LiteLLM Router          │     │
│  │ - FastAPI        │    │ - Gemini 2.5 Pro (plan/code) │     │
│  │ - scope-token    │    │ - WhiteRabbitNeo (offensive) │     │
│  │   HMAC           │    │ - Foundation-Sec-8B (sec QA) │     │
│  │ - MCP bridges    │    │ - Qwen 2.5 Coder (tool calls)│     │
│  └────────┬─────────┘    └──────────────────────────────┘     │
│           │                                                   │
│   ┌───────┼────────────────────┬──────────────┬────────────┐  │
│   ▼       ▼                    ▼              ▼            ▼  │
│ ┌─────┐ ┌──────────┐ ┌──────────────┐ ┌────────────┐ ┌──────┐ │
│ │Crack│ │ LLM-     │ │  Recon VM    │ │ Sandbox VM │ │Logger│ │
│ │ VM  │ │ Analyst  │ │  - nmap      │ │ - scratch  │ │ VM   │ │
│ │     │ │ VM       │ │  - nuclei    │ │   workspace│ │ -rsys│ │
│ │-hash│ │-llama.cpp│ │  - burp      │ │ - per      │ │  log │ │
│ │ cat │ │-ROCm/HIP │ │  - ffuf      │ │   session  │ │ TLS  │ │
│ │-RX  │ │-Fnd-Sec  │ │  - MCP       │ │            │ │      │ │
│ │7600 │ │-WRN-2.5  │ │    bridge    │ │            │ │      │ │
│ │XT   │ │          │ │              │ │            │ │      │ │
│ └─────┘ └──────────┘ └──────────────┘ └────────────┘ └──────┘ │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

## Layers

### 1. Operator layer (laptop)

Consumer Claude Code session. Used only for interactive work: reasoning, doc work, code help.

`eidolon` CLI. Thin Go or Python client that:

- Calls the Orchestrator API for session lifecycle actions.
- Invokes Claude Code subagents for per VM tool orchestration.
- Renders scope tokens, signs requests with the operator key.

### 2. Orchestrator layer (VM on Proxmox)

FastAPI service. Single operator, one session at a time.

What it owns:

- Session lifecycle (`start`, `status`, `close`)
- Scope token issuance and HMAC validation on every downstream call
- Three tier command gating (autonomous, confirm, prohibited)
- Routing model calls to LiteLLM. Never calls Anthropic.

Stateless between sessions. Session state lives on the Sandbox VM.

### 3. Model layer (LiteLLM plus GPU VM)

LiteLLM router runs as a sidecar. Single OpenAI compatible endpoint. Routes by model name:

- `gemini/gemini-2.5-pro`. Planning, report drafting, vision, analyst reasoning when the session allows egress.
- `local/whiterabbitneo-2.5-7b`. On prem analyst when the session disallows egress, or as a vendor independent fallback.
- `local/foundation-sec-8b`. Security QA, analyst role (Cisco trained).
- `local/qwen2.5-coder-14b`. Tool calling and glue.

Local models served by llama.cpp with ROCm/HIP on the RX 7600 XT inside the `llm-analyst` VM.

No commercial Anthropic endpoint in the runtime path. See [ADR 0002](../adr/0002-no-anthropic-api-runtime.md).

### 4. Per role VM layer

| VM | Core tool | Scope |
|----|-----------|-------|
| `cracker` | hashcat 6.2.6 + CrackQ | GPU bound offline workloads |
| `llm-analyst` | llama.cpp + local models | Inference endpoint for orchestrator |
| `recon` | nmap / nuclei / burp / ffuf | Active recon and web testing |
| `sandbox` | Scratch workspace | Per session workspace, cleaned on close |
| `logger` | rsyslog TLS + append only FS | Plain audit trail |
| `listener` (v0.2) | Sliver teamserver | C2 and implant handling |
| `target-sim` (v0.2) | GOAD, vulnerable apps | Safe internal lab |
| `tooling` (v0.2) | Kali heavy arsenal | Catch all operator toolbox |

See [`vm-roles.md`](./vm-roles.md) for per VM specs.

### 5. Authorization layer

Scope tokens. Issued at `eidolon session start`, carried on every agent action. HMAC validated at the orchestrator. Out of scope calls get rejected before they touch a VM.

Three tier command gating: autonomous, confirm, prohibited. See [`agent-orchestration.md`](./agent-orchestration.md).

### 6. Boundary layer

Every VM side FastAPI validates the scope token HMAC before running the requested action.

Operator workstation to host: WireGuard plus mTLS.

## Request flow (example: "crack these NTLM hashes")

1. Operator, in Claude Code: "Crack the NTLMs in `./ntds.dmp`."
2. Claude Code subagent `cracker-agent` plans the action: upload hashes, request `hashcat -m 1000`.
3. Subagent calls `eidolon run cracker crack ...`.
4. CLI attaches the session scope token and signs with the operator key.
5. Orchestrator validates the scope token, confirms the action matches the session's scope and command tier (hashcat is `autonomous`).
6. Orchestrator submits the job to the CrackQ REST API on the cracker VM.
7. CrackQ runs hashcat. SSE streams progress back through the orchestrator to the CLI.
8. Job artifacts write to the sandbox workspace.
9. Orchestrator emits a structured log to the Logger VM (rsyslog TLS).

## What Eidolon is not

Not a scanner. It orchestrates scanners.

Not a C2. v0.2+ integrates Sliver, but Eidolon itself is the lifecycle manager.

Not a SaaS. Fully on prem. No telemetry.

Not cloud first. Proxmox native. Cloud variants are post v1.

Not a client engagement platform. No LUKS per engagement, no SDN isolation, no Certificate of Destruction, no compliance mappings. Forks (Voyageur) handle those.

## Related docs

- [`vm-roles.md`](./vm-roles.md)
- [`agent-orchestration.md`](./agent-orchestration.md)
- [`provider-router.md`](./provider-router.md)
- [`gpu-strategy.md`](./gpu-strategy.md)
- [`threat-model.md`](./threat-model.md)
- [`../adr/`](../adr/)
