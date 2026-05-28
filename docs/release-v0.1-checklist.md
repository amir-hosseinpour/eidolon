# v0.1 release checklist

Status: Draft
Target: v0.1 release

## Must ship (no talk without these)

### Repository

- [ ] Public GitHub repo under the eidolon org, MIT licensed
- [ ] README.md public and accurate
- [ ] PRD.md published
- [ ] ROADMAP.md published
- [ ] CONTRIBUTING.md with PR flow
- [ ] SECURITY.md with disclosure policy and live security email
- [ ] CODE_OF_CONDUCT.md
- [ ] LICENSE (MIT)
- [ ] All ADRs (0001 through 0007) in `docs/adr/`

### Architecture docs

- [ ] `docs/architecture/overview.md`
- [ ] `docs/architecture/vm-roles.md`
- [ ] `docs/architecture/agent-orchestration.md`
- [ ] `docs/architecture/provider-router.md`
- [ ] `docs/architecture/threat-model.md`
- [ ] `docs/architecture/gpu-strategy.md`

### Diagrams (rendered SVG, source D2)

- [ ] `docs/diagrams/architecture-overview`
- [ ] `docs/diagrams/session-lifecycle`
- [ ] `docs/diagrams/agent-orchestration`
- [ ] `docs/diagrams/provider-router`

### Core VMs

- [ ] Cracker VM provisioning (`vms/cracker/`)
 - [ ] `provision.sh` idempotent
 - [ ] cloud-init for Ubuntu 24.04
 - [ ] hashcat 6.2.6 OpenCL verified against the RX 7600 XT
 - [ ] CrackQ REST API reachable from orchestrator
 - [ ] 2 TB wordlist volume mounted read only
- [ ] LLM Analyst VM provisioning (`vms/llm-analyst/`)
 - [ ] llama.cpp server with OpenAI compat endpoint
 - [ ] WhiteRabbitNeo 2.5 7B loaded and answering
 - [ ] Foundation Sec 8B loaded and answering
 - [ ] Latency target: first token under 500 ms on a 7B model
- [ ] Recon VM provisioning (`vms/recon/`)
 - [ ] Kali base image
 - [ ] nmap, nuclei, burp, ffuf installed
 - [ ] MCP bridge answering tool calls
- [ ] Sandbox VM provisioning (`vms/sandbox/`)
 - [ ] Minimal Ubuntu 24.04
 - [ ] Workspace volume scheme
- [ ] Logger VM provisioning (`vms/logger/`)
 - [ ] rsyslog TLS endpoint on 6514
 - [ ] Append only log directory with `chattr +a`

### Orchestrator

- [ ] FastAPI service skeleton (`orchestrator/`)
- [ ] Scope token HMAC issuance and validation
- [ ] Session lifecycle endpoints (`start`, `status`, `close`)
- [ ] Three tier command gating enforced at the orchestrator
- [ ] mTLS to VM job servers
- [ ] Routing to LiteLLM

### CLI

- [ ] `eidolon session start|close|status`
- [ ] `eidolon run <vm> <tool>`
- [ ] `eidolon session logs` pulls from Logger VM
- [ ] Signed requests with operator key

### LiteLLM router

- [ ] Declarative YAML config
- [ ] Gemini 2.5 Pro wired
- [ ] WhiteRabbitNeo and Foundation Sec 8B wired
- [ ] Per session cost tracking to Postgres

### Subagent definitions

- [ ] `cracker-agent`
- [ ] `recon-agent`
- [ ] `analyst-agent`
- [ ] `sandbox-agent`
- [ ] `report-agent`

### Demo readiness

- [ ] GOAD lab provisioned, snapshotted clean
- [ ] Demo scope doc tested
- [ ] Full kill chain reproducible in under 10 minutes
- [ ] Backup pre recorded demo video
- [ ] Second demo laptop with the same state in case the primary breaks

## Should ship (nice to have, not blocking)

- [ ] `docs/runbooks/start-session.md`
- [ ] `docs/runbooks/close-session.md`
- [ ] `docs/runbooks/add-vm.md` (exists, polish)
- [ ] Ansible playbook for fresh Proxmox install
- [ ] Scope doc schema published with example
- [ ] CHANGELOG.md with v0.1 notes

## Can wait (post v0.1)

- Tooling VM (v0.2)
- Target Sim VM (v0.2)
- Listener VM (v0.2)
- Scope token HMAC validation at every VM boundary (v0.2 hardening)
- Three tier command gating at VM boundary (defense in depth, v0.2)
- Langfuse integration
- Packaged installer
- Operator handbook
- Public security audit

## Pre talk rehearsal

One week before the talk:

- [ ] Full demo from cold boot at least 3 times
- [ ] Demo on the actual laptop that will be on stage
- [ ] Test network conditions at venue if accessible, fall back if not
- [ ] Slide deck finalized
- [ ] Talk rehearsed at full time (40 minutes) with a live audience (colleagues, friends)
- [ ] Demo backup video verified plays correctly

Day before the talk:

- [ ] VMs snapshotted to clean state
- [ ] Claude Code subagents loaded and tested
- [ ] WireGuard tunnel tested from venue network
- [ ] Power adapter, HDMI adapter, USB C hub, backup laptop in bag
- [ ] Phone hotspot configured as backup internet

Day of the talk:

- [ ] Arrive 45 minutes before talk
- [ ] Test audio and video on stage
- [ ] Confirm laptop can connect to venue network
- [ ] Stage water ready
