# Eidolon

I built Eidolon to drive AI agents through real pentests without losing context between engagements or drowning in permission prompts. It is a templated multi-VM workspace orchestrator for offensive security work.

The setup: take a Proxmox box, split it into role-scoped VMs, point Claude Code at the orchestrator from your laptop. The AI runs the rote work. You handle the decisions that matter.

No SaaS. No vendor lock-in. No client dependency.

## Status

v0.1-rc1. Working but young. Use it on lab targets, on engagements you own, on authorized work. Not battle-tested across hundreds of engagements yet.

## Who this is for

If you're a solo pentester with a homelab, one Proxmox host and your laptop is enough. Eidolon ties your tools together so a Claude Code session can recon a web app on Tuesday and pivot to AD on Wednesday without leaking context between them.

If you're a security researcher, it gives you a reproducible, observable, hackable environment for TTP validation, malware triage, exploit dev, or offensive-AI experiments against known-vulnerable targets.

If you're a firm and you want an engine to fork, Eidolon is MIT-licensed and built for it. Layer your client intake, compliance overlays, and branded reports on top. Your firm-specific work stays private.

## What it is not

Not a scanner. Not a C2. Not a compliance product. Not a managed platform. Not something you point at a paid engagement on its own.

The firm-grade workflows (client isolation, signed Certificate of Destruction, multi-engagement concurrency, engagement memory, compliance mappings) live in forks. That separation is on purpose. The generic plumbing belongs upstream. The opinionated firm stuff belongs in your fork.

## How it works

- One VM per role. Recon, exploit, crack, analyze, listen, stage. Each has its own scoped subagent and tool set.
- Every agent action carries a signed scope token. Out-of-scope calls get rejected at the orchestrator before they touch a VM.
- Three command tiers: autonomous (just runs), confirm (operator approves), prohibited (blocked, full stop). Destructive actions require a human gate.
- Model-agnostic. LiteLLM fronts a commercial provider (Gemini by default) plus local models (WhiteRabbitNeo, Foundation Sec 8B, Qwen2.5 Coder). Routing follows your session's egress policy, not what a given model is willing to answer.
- Audit log is hash-chained. Tampering breaks the chain.

![Architecture overview](docs/diagrams/architecture-overview.svg)

Each VM runs a FastAPI job server. Long jobs (cracks, scans) stream progress over SSE. Claude Code on the operator's laptop spawns one subagent per VM and stitches the results together.

More diagrams in [`docs/diagrams/`](docs/diagrams/).

## Quick start

```bash
git clone https://github.com/amir-hosseinpour/eidolon
cd eidolon
pip install -e ".[dev]"
```

On the orchestrator host (your laptop is fine for solo work):

```bash
eidolon orchestrator init     # writes ~/.eidolon/orchestrator-token
eidolon orchestrator start    # listens on http://127.0.0.1:8000
```

On the operator laptop:

```bash
eidolon login \
  --host http://orch.local:8000/v1 \
  --token "$(cat ~/.eidolon/orchestrator-token)"
claude mcp add eidolon eidolon-mcp
```

Open an engagement against your local Juice Shop:

```bash
eidolon engage start --slug js-test --purpose pentest
eidolon engage scope <ENG_ID> \
  --target 172.17.0.0/16 \
  --permit recon.read \
  --tier confirm \
  --ttl 4h
eidolon engage provision <ENG_ID> --template web-app-pentest
```

Drive it from Claude Code: *"Start a web-app pentest using `web-app-pentest`, slug js-test, scope 172.17.0.0/16."* Approve the decision forks as they pop up.

Tear it down (close keeps the workspace, erase wipes it):

```bash
eidolon engage teardown <ENG_ID>     # destroy VMs + network
eidolon engage erase    <ENG_ID>     # close + teardown + mark erased
```

Full walkthrough: [`docs/runbooks/dogfood-web-app.md`](docs/runbooks/dogfood-web-app.md).

## Documentation

| Path | Purpose |
|------|---------|
| [`docs/BLUEPRINT-V0.1.md`](docs/BLUEPRINT-V0.1.md) | Plan of record for v0.1 |
| [`docs/concepts.md`](docs/concepts.md) | Engagements, workspaces, scope tokens, decision forks, secrets, substrates |
| [`docs/decision-forks.md`](docs/decision-forks.md) | The five fork types, when each fires, who resolves them |
| [`docs/templates.md`](docs/templates.md) | How to author an engagement template |
| [`docs/api.md`](docs/api.md) | REST endpoints + MCP tool reference |
| [`docs/runbooks/dogfood-web-app.md`](docs/runbooks/dogfood-web-app.md) | End-to-end web-app pentest runbook |
| [`docs/runbooks/dogfood-ad.md`](docs/runbooks/dogfood-ad.md) | End-to-end AD recon runbook (Proxmox) |
| [`PRD.md`](PRD.md) | Product requirements |
| [`ROADMAP.md`](ROADMAP.md) | Phased release plan |
| [`docs/architecture/`](docs/architecture/) | System architecture, VM specs, router, agents |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records |

## Forks

Eidolon is built to be forked. Your firm-specific work layers on top without touching the core. Client intake, compliance overlays, branded reports, client-isolation orchestration, signed Certificates of Destruction, multi-engagement concurrency, engagement memory: all of that lives in your fork, not upstream.

## Prior art

I learned a lot reading other people's work. Pieces of Eidolon owe something to:

- [CAI](https://github.com/aliasrobotics/CAI) for kill chain taxonomy and agent patterns
- [GOAD](https://github.com/Orange-Cyberdefense/GOAD) for Proxmox target lab provisioning
- [PentestGPT](https://github.com/GreyDGL/PentestGPT) for three-module session isolation
- [Ghostwriter](https://github.com/GhostManager/Ghostwriter) for the engagement data model

## License

MIT. See [LICENSE](LICENSE).

## Security

For responsible disclosure of Eidolon vulnerabilities, see [SECURITY.md](SECURITY.md).
