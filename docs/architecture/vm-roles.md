# Eidolon, VM role inventory

Status: Draft, v0.1 spec
Last updated: 2026-04-20

Each VM is single purpose. Agents are scoped to one VM. Tools are scoped to an agent.

## v0.1 VMs (MVP)

### 1. Cracker VM (`cracker`)

Purpose: offline GPU bound work. Hashes, password spraying prep, archive cracking.

Specs:

- OS: Ubuntu Server 24.04 LTS
- vCPU: 8. RAM: 16 GB. Disk: 80 GB plus 2 TB wordlist volume (shared read only).
- GPU: PCIe passthrough of RX 7600 XT (16 GB VRAM).

Stack:

- `hashcat` 6.2.6, OpenCL backend (AMDGPU PRO OpenCL driver)
- `CrackQ`, REST API orchestrator around hashcat ([here](https://github.com/f0cker/crackq))
- `john` for formats hashcat doesn't cover
- `hcxtools` for WPA handshake conversion
- Local FastAPI job server (`vms/cracker/`)

Wordlists (read only volume):

- rockyou, crackstation, SecLists, Have I Been Pwned NT hashes
- Operator drops custom wordlists into the session workspace at job time

Why the split:

GPU passthrough binds one GPU to one VM. Cracker and LLM Analyst cannot share the 7600 XT. See [`gpu-strategy.md`](./gpu-strategy.md).

CrackQ over Hashtopolis because the op is single node. Hashtopolis's multi agent protocol is noise for one box.

Agent: `cracker-agent`

- Tools: `crack_hashes`, `identify_hash_type`, `estimate_runtime`, `import_wordlist`
- Gate: `autonomous` (hashcat is CPU/GPU bound with no network scope concern)

### 2. LLM Analyst VM (`llm-analyst`)

Purpose: serve local offensive and security tuned models as an OpenAI compat endpoint to the LiteLLM router.

Specs:

- OS: Ubuntu Server 24.04 LTS
- vCPU: 8. RAM: 32 GB. Disk: 200 GB (models are big).
- GPU: shares RX 7600 XT with cracker? No. See GPU strategy. 7600 XT stays dedicated to cracker.
 - v0.1 LLM Analyst runs on CPU only, or on the Arc A380 via Vulkan (slower but fine for 7B models).
 - After GPU upgrade: RTX PRO 6000 Blackwell (96 GB VRAM) dedicated to LLM Analyst.

Stack:

- `llama.cpp` server (HTTP mode, `server` binary), OpenAI compat
- ROCm/HIP build on AMD. CUDA build on RTX PRO 6000. Vulkan fallback on Arc.
- Models (GGUF, Q4_K_M or Q5_K_M depending on RAM):
 - `WhiteRabbitNeo-2.5-7B`, security tuned, used when the session disallows egress or as a vendor independent fallback
 - `Foundation-Sec-8B`, Cisco's security tuned Llama 3.1
 - `Qwen2.5-Coder-14B`, tool calling, code
 - Optional: `Llama-3.3-70B-Instruct-Q4` once the GPU upgrade lands

Interface:

- OpenAI compat HTTP at `:8080/v1/chat/completions`
- LiteLLM router consumes this as a `local/*` provider

Why this VM is separate:

- Heavy inference stays away from orchestrator crashes.
- Model updates don't touch the production orchestrator.
- Future: swap the GPU or add more model serving VMs without touching anything else.

Agent: none directly. LLM Analyst is a service, not an operator interface.

### 3. Recon VM (`recon`)

Purpose: active recon and web application testing inside the session's scoped network.

Specs:

- OS: Kali Linux 2026.x (rolling)
- vCPU: 4. RAM: 8 GB. Disk: 60 GB.
- NICs: 2. Management (mgmt VNET), session target NIC.

Stack:

- `nmap` 7.94+ with NSE scripts
- `nuclei` with templates (auto updated)
- `burpsuite` pro (licensed. Headless via `burprest` or interactive via X forwarding)
- `ffuf`, `gobuster`, `httpx`, `katana`
- `subfinder`, `amass`
- MCP bridge (`vms/recon/mcp-server.py`). Exposes tool calls to Claude Code subagents.

Network posture:

- Egress filter on the target NIC. In scope CIDR only.
- Mgmt NIC reaches only the orchestrator.
- No cross session state. Between sessions the recon VM rolls back to a clean snapshot of its mgmt and tooling state.

Agent: `recon-agent`

- Tools: `scan_ports`, `enumerate_services`, `run_nuclei`, `web_fuzz`, `subdomain_enum`
- Gate: `confirm` for any scan touching more than 256 hosts. `autonomous` otherwise.
- Prohibited: any target outside the session's scope.

### 4. Sandbox VM (`sandbox`)

Purpose: per session scratch workspace. Files, notes, intermediate artifacts, tool output. One instance per active session.

Specs:

- Template: Ubuntu Server 24.04 LTS, minimal
- vCPU: 2. RAM: 4 GB.
- Disk: thin provisioned, session scoped.

Behavior:

- `eidolon session start` provisions a clean workspace on the sandbox VM.
- Tool output, notes, and draft artifacts live here for the life of the session.
- `eidolon session close` tears the workspace down. Anything the operator wants to keep gets archived out beforehand.

Eidolon does not ship cryptographic erase, per session encrypted volumes, or forensic artifact handling. Firm forks layer those on top.

Agent: `sandbox-agent`

- Tools: `write_note`, `read_artifacts`, `export_to_report_tmpl`
- Gate: `autonomous`, scoped to the active session workspace.

### 5. Logger VM (`logger`)

Purpose: append only audit trail for every orchestrator and agent action.

Specs:

- OS: Ubuntu Server 24.04 LTS, hardened
- vCPU: 2. RAM: 4 GB. Disk: 500 GB (append only).
- Filesystem flag: `chattr +a` on the log directory.

Stack:

- `rsyslog` listens on TCP 6514 with TLS (mutual auth)
- Structured JSON log records with scope token hash, actor, target, command, exit status
- Operator pulls session log excerpts from the CLI (`eidolon session logs`)

Eidolon does not ship signed logs, GPG chain of custody, or forensic grade retention. Forks that need those (downstream forks) layer them on top.

Access pattern:

Everything gets written through rsyslog. Reads happen via the orchestrator. No agent has direct read or write access to the logger VM filesystem.

Why it's separate:

- A compromised orchestrator cannot silently drop log records that were already shipped.
- Logs can be exported as a session archive at close without touching the orchestrator's state.

Agent: none. Logger is receive only by design.

## v0.2 VMs

### 6. Target Sim VM (`target-sim`)

Purpose: disposable, auto provisioned vulnerable lab for dry runs, training, agent validation.

- Base: [GOAD](https://github.com/Orange-Cyberdefense/GOAD) Proxmox provisioning
- Vulnerable apps library (juice shop, dvwa, OWASP Top 10 targets)
- Always on a dedicated `sim` SDN VNET. Never routable to real targets.

### 7. Listener VM (`listener`)

Purpose: 24/7 C2 infrastructure.

- Base: Debian 12
- Stack: `Sliver` teamserver, WireGuard ingress, redirector (Caddy or nginx)
- Per session profile. Implants signed with a session scoped CA.
- Listener traffic egresses via a VPN scoped to the session target.

### 8. Tooling VM (`tooling`)

Purpose: Kali heavy catch all for anything the Recon VM doesn't carry. Operator driven, not agent driven.

- Base: Kali rolling
- Preloaded: impacket, crackmapexec, bloodhound, responder, mitm6, evil winrm, sqlmap, and friends
- Interactive only. No scope tokenized agent access in v0.2.

## Agent to VM matrix

| Agent | VM | Gate tier | Prohibited |
|-------|-----|-----------|------------|
| `cracker-agent` | cracker | autonomous | Out of scope hashes |
| `recon-agent` | recon | autonomous (under 256 hosts), confirm (over 256) | Out of scope CIDR, DoS tools |
| `sandbox-agent` | sandbox | autonomous | Writes outside the active session workspace |
| `listener-agent` (v0.2) | listener | confirm | Spawning new implants |
| `report-agent` | sandbox or orchestrator | autonomous | Reading workspaces from other sessions |

## Sizing and host guidance

Minimum host for v0.1:

- CPU: 16 cores, 32 threads (Ryzen 9 7950X or better)
- RAM: 64 GB (128 GB once LLM Analyst is GPU accelerated)
- Storage: 2x NVMe (host OS plus VM disks), 2x SATA SSD mirror (wordlists, logs)
- GPU: 1x RX 7600 XT (cracker) plus 1x Arc A380 (display and LLM fallback)
- NICs: 2x 2.5 GbE (mgmt plus session target uplink)
- UPS: 1500 VA minimum. Long cracks are expensive to lose.

Target host for v1.0:

- Same CPU and RAM floor
- GPU: 1x RTX PRO 6000 Blackwell (96 GB VRAM) dedicated to LLM Analyst
- GPU: keep the RX 7600 XT on cracker
- Storage: add RAIDZ2 for wordlists and logs
