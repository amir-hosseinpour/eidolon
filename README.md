# Eidolon

Local environment for offensive security work. Pentesters and security researchers drive role specialized VMs on a Proxmox box from a laptop. AI agents handle the rote work. No SaaS, no vendor lock in, no client dependency.

## What it is

Eidolon takes one Proxmox server and splits it into role specialized VMs that AI agents on the operator's workstation drive. Each VM owns one job. GPU password cracking on one. Local LLM analysis on another. Recon, target simulation, listener, sandbox, logger. Each role has an agent with scoped tools and a shared audit log.

Eidolon is a framework, not a platform. It is the plumbing that ties hashcat, nmap, metasploit, burp, sliver, a commercial LLM via LiteLLM for egress-allowed sessions, and local LLMs (WhiteRabbitNeo, Foundation Sec, Qwen Coder) for egress-denied sessions into one workflow for a single pentester or researcher.

It is not a scanner. It is not a C2. It is not a compliance product. It does not run paid client engagements on its own. Firm grade features (client isolation, signed Certificate of Destruction, multi engagement concurrency, engagement memory, compliance mappings) live in proprietary forks built on top. White Tuque's Voyageur is the canonical reference.

## Status

Alpha. Active development. Not production ready. Public release is tracked for v0.1 alongside a talk at DefCon Toronto in May 2026.

## Who it is for

Independent pentesters running home labs. One Proxmox box, one operator, tools you already use, AI agents that handle the rote work.

Security researchers. TTP validation, malware triage, exploit development, offensive AI agent experiments against known vulnerable targets. Reproducible, observable, hackable.

Firms who want a shared engine for their proprietary platform. Eidolon is MIT. Fork it, layer your workflow on top, keep your firm specific work private. Voyageur shows one way.

## Key properties

Operator on laptop. Claude Code runs on your Mac. The server is dumb infrastructure.

Model agnostic. LiteLLM fronts a commercial provider (Gemini by default) and local models (WhiteRabbitNeo, Foundation Sec 8B, Qwen2.5 Coder), or any OpenAI compatible endpoint. Routing is driven by the session's egress policy, not by what a given model will or will not answer. Swap providers, agent code keeps working.

One VM per kill chain phase. Recon, exploit, crack, analyze, listen, stage. Each is its own VM with its own scoped subagent and tool set.

Scope tokens. Every agent action carries a signed scope token. Out of scope calls get rejected at the orchestrator.

Three tier command gating. Autonomous, confirm, prohibited. Destructive commands require a human gate.

Fork friendly by design. MIT license, stable overlay points, clean separation between generic framework and firm specific work.

Proxmox native. Runs on Proxmox VE 8+ on commodity hardware. No enterprise virtualization license needed.

## Architecture

![Architecture overview](docs/diagrams/architecture-overview.svg)

Each VM runs a FastAPI job server scoped to its role. Jobs carry a signed scope token. Long running jobs (crack, scan) stream progress back over SSE. The operator's Claude Code sends subagents per VM and pulls results together.

More diagrams in [`docs/diagrams/`](docs/diagrams/): session lifecycle, agent orchestration, provider router.

## Quick start (v0.1)

Eidolon ships an orchestrator (FastAPI), an operator CLI, a Claude Code skills
pack, an MCP server, and an in-VM agent. Pick one machine to run the
orchestrator on (laptop is fine for solo work, dedicated VM is fine for shared
work). Then connect from anywhere.

Install:

```bash
git clone https://github.com/amir-hosseinpour/eidolon
cd eidolon
pip install -e ".[dev]"
```

On the orchestrator host:

```bash
eidolon orchestrator init     # generates ~/.eidolon/orchestrator-token
eidolon orchestrator start    # http://127.0.0.1:8000
```

On the operator laptop (same machine for solo work):

```bash
eidolon login \
  --host http://orch.local:8000/v1 \
  --token "$(cat ~/.eidolon/orchestrator-token)"
# laptop.json + ~/.claude/skills/eidolon-* installed
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

Drive it from Claude Code: "Start a web-app pentest using `web-app-pentest`,
slug js-test, scope 172.17.0.0/16" and approve forks as they pop up.

Tear down (close keeps VMs; erase nukes everything):

```bash
eidolon engage teardown <ENG_ID>      # destroy VMs + network, keep workspace
eidolon engage erase   <ENG_ID>       # close + teardown + mark erased
```

Full walkthrough: [`docs/runbooks/dogfood-web-app.md`](docs/runbooks/dogfood-web-app.md).

## Documentation

| Path | Purpose |
|------|---------|
| [`docs/BLUEPRINT-V0.1.md`](docs/BLUEPRINT-V0.1.md) | Plan-of-record for v0.1 (this is what is being built) |
| [`docs/concepts.md`](docs/concepts.md) | Engagements, workspaces, scope tokens, decision forks, secrets, substrates |
| [`docs/templates.md`](docs/templates.md) | How to author an engagement template |
| [`docs/decision-forks.md`](docs/decision-forks.md) | The five fork types, when each fires, who resolves them |
| [`docs/api.md`](docs/api.md) | REST endpoints + MCP tool reference |
| [`docs/runbooks/dogfood-web-app.md`](docs/runbooks/dogfood-web-app.md) | End-to-end web-app pentest dogfood runbook |
| [`docs/runbooks/dogfood-ad.md`](docs/runbooks/dogfood-ad.md) | End-to-end AD recon dogfood runbook (Proxmox) |
| [`PRD.md`](PRD.md) | Product requirements (legacy v0 framing) |
| [`ROADMAP.md`](ROADMAP.md) | Phased release plan |
| [`docs/architecture/`](docs/architecture/) | System architecture, VM specs, router, agents |
| [`docs/diagrams/`](docs/diagrams/) | Rendered diagrams (D2 source + SVG) |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records |
| [`docs/runbooks/`](docs/runbooks/) | Session and research playbooks |
| [`docs/future/`](docs/future/) | Roadmap features (Paperclip orchestrator, etc.) |

## Talks

DefCon Toronto, May 2026. Local AI driven offensive security: building a pentest and research environment on commodity hardware. Public release of Eidolon coincides with the talk.

## Forks

Eidolon is designed to be forked. Your firm specific work (branding, client intake, compliance overlays, evidence handling) layers on top without touching the core.

Known forks:

- Voyageur (URL TBD): White Tuque's in-house AI companion pentester. Adds client isolation, compliance, multi engagement concurrency, engagement memory, branded reports.

## Credits

Forked from a personal homelab scaffold and rewritten for offensive security work. Inspiration and prior art:

- [CAI](https://github.com/aliasrobotics/CAI): kill chain taxonomy and agent patterns
- [GOAD](https://github.com/Orange-Cyberdefense/GOAD): Proxmox target lab provisioning
- [PentestGPT](https://github.com/GreyDGL/PentestGPT): three module session isolation
- [Ghostwriter](https://github.com/GhostManager/Ghostwriter): engagement data model

## License

MIT. See [LICENSE](LICENSE).

## Security

For responsible disclosure of Eidolon vulnerabilities, read [SECURITY.md](SECURITY.md).
