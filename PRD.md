# Eidolon, product requirements document

Status: Draft v0.1
Last updated: 2026-04-26

## 0. v0.1 scope cut (read first)

v0.1 ships the **control plane only** — engagement-scoped scope tokens, three-tier command gate with operator co-sign, append-only hash-chained audit log, hybrid LLM router with redaction, and Certificate of Destruction attestation. v0.1 does **not** ship VMs. Operators bring their own runtime via the `HypervisorBackend` interface (Docker recipe in v0.1 docs; Proxmox / vSphere / libvirt in v0.2+). The six homelab VM roles previously planned for v0.1 (Engagement, Logger, Recon, Web, Internal, Wireless) move to Voyageur and to ROADMAP v0.2+. Rationale and prior-art comparison: ADR 0008.

## 1. Vision

The governance layer for AI-driven offensive security work. Runtime-agnostic. Open source under MIT. The hard problems Eidolon solves are: per-engagement identity binding, three-tier command authorization with operator co-sign at the prohibited tier, hash-chained audit attestation, redaction-aware hybrid LLM routing, and cryptographic-erase Certificate of Destruction. The runtime that actually executes commands is bring-your-own — Docker, Proxmox, vSphere, libvirt, bare metal, or a managed offering like Voyageur.

Public release of v0.1 is targeted for DefCon Toronto in May 2026. The design and the docs are built to stand up to a room of working pentesters and researchers.

Eidolon is a framework, not a platform. Firm-grade workflows (managed VMs, client isolation orchestration, compliance, multi-engagement, engagement memory, reports) live in proprietary forks layered on top. Voyageur is the canonical reference fork.

## 2. Problem

Independent pentesters and security researchers hit two structural problems.

1. Tools are a patchwork. Hashcat on one box, Burp on another, recon in a terminal, notes in Obsidian. Nothing coordinates. Context dies between phases.
2. AI automation is either missing or unsafe. Existing AI pentest agents (PentestGPT, PentAGI, CAI) run in one container, treat the host as a blob, and have no scope enforcement.

Commercial alternatives (Pentera, Horizon3.ai) solve parts of this behind closed SaaS at thirty to fifty thousand dollars a year per seat. No self hosted, hackable equivalent exists.

## 3. Users

Primary A: independent pentester running a home lab. Owns a Proxmox box already or willing to build one. Comfortable on Linux, Proxmox, CLI. Uses Claude Code (or similar) daily. Wants recon, cracking, and analysis automated without signing into yet another SaaS.

Primary B: security researcher. Uses Eidolon as a lab for TTP validation, malware triage, exploit development, and offensive AI agent experiments against known vulnerable targets. Cares about reproducibility, observability, MCP tool integration.

Secondary: pentest firm engineer. Forks Eidolon to build a firm internal platform with firm branding, client intake, compliance overlays, and evidence handling layered on top. Voyageur is the canonical example. The firm's work stays private, generic improvements flow back upstream.

## 4. Non goals

Not a vulnerability scanner. Eidolon mediates calls to nmap, nuclei, burp via the tool router. It does not replace them.

Not a C2 framework. Eidolon mediates command authorization. The C2 (Sliver, Mythic) is BYO via the runtime backend.

Not an exploit database. No CVE catalog, no Metasploit-style module registry. Tools bring their own data.

Not a report-writing AI. Drafting is one capability behind the LLM router, not the product.

Not a VM bundle. Eidolon v0.1 ships zero VMs. Operators wire their own runtime via the `HypervisorBackend` interface. Reference backends ship in v0.2+. Voyageur ships a managed Proxmox runtime as a commercial offering.

Not a compliance product. Eidolon emits the Certificate of Destruction (signed JSON anchored to audit head hashes) and the hash-chained audit trail; it does not map those to PIPEDA, SOC 2, or any specific regime. Compliance mappings live in firm forks.

Not a multi-engagement platform in v0.1. One engagement at a time. Multi-engagement concurrency with bubble isolation is a Voyageur feature.

Not Windows host in v0.1. Operator runs on macOS or Linux. Windows support follows the codex-rs sandbox pattern in v0.4+.

Not tied to one AI vendor. Runtime agents must stay model-agnostic via the LiteLLM router.

## 5. Functional requirements

### 5.1 Session lifecycle

| Requirement | Priority |
|---|---|
| `eidolon session start <slug>` provisions a clean session workspace and scope token | P0 |
| Session metadata (purpose, target range, operator, start time) captured in a structured record | P0 |
| Every agent action during the session carries the scope token | P0 |
| `eidolon session close <session-id>` tears down workspace and archives session logs | P0 |
| Session purpose field supports `pentest`, `research`, `ctf`, `training` | P0 |

Scope tokens are authorization only. They say what the agent can touch. They do not imply any contract, client relationship, or compliance artifact. Those concerns belong to forks.

### 5.2 Hypervisor backend interface

| Requirement | Priority |
|---|---|
| `HypervisorBackend` Python interface defined in v0.1 (open / scope / dispatch / close / erase / attest hooks) | P0 |
| One stub backend (`NoOpBackend`) that exercises the full lifecycle without launching real VMs, used for tests and demos | P0 |
| Docker BYO recipe documented in `docs/runbooks/byo-docker.md` | P1 |
| Proxmox backend | v0.2 |
| codex-rs Windows AppContainer sandbox backend | v0.4 |
| macOS Virtualization.framework backend | v0.5 |
| Six original homelab VM roles (Engagement, Logger, Recon, Web, Internal, Wireless) | Voyageur |

### 5.3 Agent orchestration

| Requirement | Priority |
|---|---|
| Each VM runs a FastAPI job server | P0 |
| Operator dispatches subagents via Claude Code with scoped tool access per VM | P0 |
| Long running jobs return a job ID and stream events over SSE | P0 |
| Agents cannot exceed the scope token's declared target set | P0 |
| Three tier command gating: autonomous, confirm, prohibited | P0 |
| Agent memory is per session, not global, and does not persist after close | P1 |

### 5.4 Provider router

| Requirement | Priority |
|---|---|
| LiteLLM proxy routes model calls for every runtime agent | P0 |
| At least one commercial provider (Gemini API) and one local model (WhiteRabbitNeo 2.5) covering the egress-denied path | P0 |
| No commercial Anthropic API in the runtime path | P0 |
| Router config is declarative (YAML), swappable per session | P1 |

### 5.5 Audit and attestation

| Requirement | Priority |
|---|---|
| Every scope-token-bearing call appends one entry to the audit log: seq, ts, engagement_id, operator_id, action, target, tier, result, prev_hash, hash | P0 |
| Hash chain: `hash = sha256(prev_hash || canonical_json(entry_minus_hash))` | P0 |
| `eidolon audit verify <engagement_id>` walks the chain, returns OK or first broken index | P0 |
| Daily rotation: chain segment closed at UTC midnight, Ed25519-signed, new segment continues prev_hash | P0 |
| Logs accessible from the operator's CLI during and after the engagement | P0 |
| Certificate of Destruction (signed JSON + stub PDF) embeds: engagement UUID, head hash at open, head hash at close, Ed25519 signature over both | P0 |
| Real LUKS volume orchestration to back the Cert of Destruction | Voyageur |
| Mapping to PIPEDA / SOC 2 / PCI controls | Forks |

## 6. Non functional requirements

| Area | Requirement |
|---|---|
| Security | All secrets in the operator's local vault. All inter VM traffic authenticated with mTLS. |
| Reliability | Session lifecycle is idempotent. Partial failures leave the system recoverable. |
| Observability | Every tool call, agent decision, and scope check logged with scope token, timestamp, SHA of inputs. |
| Performance | Recon scan of a /24 under 10 min. Crack job submission latency under 2 s. First token on a 7B local model under 500 ms. |
| Portability | Runs on Proxmox VE 8+ on x86 64. Single node deployment. No Kubernetes. No cloud dep at runtime. |
| Licensing | MIT for code. Docs CC BY 4.0. No GPL in runtime path. |

## 7. Success metrics (v1.0)

The operator can provision a fresh session and start recon within 5 minutes of `eidolon session start`.

A crack job on a 100k hash NTLM file returns a status URL in under 2 seconds and streams progress back to the session.

Session close tears down workspace and archives logs in under 30 seconds.

500 GitHub stars or 3 known production forks (Voyageur counts as one), whichever comes first.

A demo at DefCon Toronto May 2026 completes the kill chain (recon, crack, analyst summary) against a GOAD lab inside 10 minutes, live, without breaking.

## 8. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Local LLMs not capable enough for complex agent reasoning | High | Hybrid router. Commercial provider by default, local for egress-denied sessions. Benchmark every release. |
| Runtime AI provider changes ToS mid session | High | Model agnostic router is the invariant. Never hardcode a provider. |
| Operator laptop compromised, research data exposed | Medium | Session data stays server side. Laptop only holds session state. FileVault required. |
| Agent runs destructive commands against out of scope targets | High | Scope tokens plus per VM firewall rules. Tier 3 prohibited commands hard blocked at the FastAPI layer, not at the agent. |
| Project loses maintainer interest | Medium | Hackable by design. ADRs. Fork friendly license. Voyageur and other known forks hedge single maintainer risk. |
| People mistake Eidolon for a compliance product | Medium | Docs are loud about the boundary. Forks handle compliance. |

## 9. Out of scope for v0.1

Six homelab VMs (Engagement, Logger, Recon, Web, Internal, Wireless). BYO via `HypervisorBackend` or run Voyageur for managed.
Real LUKS per-engagement volume orchestration and cryptographic erase. v0.1 emits the *attestation*; the volume itself is BYO. Voyageur ships managed LUKS.
Proxmox SDN per-engagement VNETs. Voyageur ships managed networking.
chattr +a Logger VM with TLS rsyslog. v0.1 uses POSIX append on local disk. Voyageur ships immutable Logger.
Multi-engagement concurrency, web UI, REPL. v0.1 is single engagement, CLI only.
Engagement memory (persistent, queryable context across engagements). Forks.
Log curation (noise stripping, evidence indexing). Forks.
Compliance mappings (PIPEDA, Bill 25, GDPR, SOC 2, PCI DSS, CREST). Forks.
Multi-operator collaboration beyond two-person co-sign at prohibited tier. Forks.
Cloud-hosted SaaS mode. Forks.
Windows host operator workstation. v0.4+ via codex-rs sandbox pattern.

## 10. Open questions

Where should the scope-from-slug converter live in the CLI?

Do we ship a reference hardware spec or leave operators to pick?

How do we benchmark agent effectiveness across model backends? (See `docs/future/benchmarking.md`, TODO.)

What is the minimum demo story for DefCon? (See `docs/presentations/defcon-toronto-2026-demo-plan.md`.)

See [`ROADMAP.md`](ROADMAP.md) for release milestones and [`docs/adr/`](docs/adr/) for architectural decisions.
