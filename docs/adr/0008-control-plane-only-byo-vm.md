# ADR 0008: v0.1 ships the control plane only — bring your own VM

Status: Accepted
Date: 2026-04-26
Supersedes (in part): ADR 0001 — the homelab VM bundle is no longer in v0.1 scope

## Context

The original Eidolon scaffold inherited six VM roles from the homelab fork (Engagement, Logger, Recon, Web, Internal, Wireless). These directories under `vms/` are currently empty placeholders. Spinning each VM up to a usable, reproducible state is weeks of work per VM and reproduces what existing platforms already solve well: E2B, Daytona, Firecracker, Docker, plain Proxmox templates, and Terraform-driven libvirt all ship runtime sandboxes today.

What none of those platforms ship is the **control plane** that mediates AI agent access to those sandboxes — engagement-scoped identity binding, three-tier command gating with operator authorization at the prohibited tier, hash-chained audit attestation, cryptographic-erase Certificate of Destruction, and redaction-aware hybrid LLM routing. That gap is what makes Eidolon defensible as an open-source project.

Two contemporaneous data points sharpened this decision:

1. **PentAGI** (vxcontrol/pentagi, 15.8k stars, MIT, active) ships the agent-execution piece without any governance layer. The April 2026 Checkpoint Research write-up of HexStrike-AI being weaponized for zero-day exploitation is the existence proof that "AI pentest tooling without a governance layer" is not a product, it's a liability.
2. **Microsoft Agent Governance Toolkit** (released 2026-04-02, MIT) ships several governance primitives Eidolon planned to ship — execution rings, capability sandboxing, hash-chained append-only audit, Ed25519 plugin signing, quorum approval. AGT has zero concept of a time-bounded engagement, no LUKS / crypto-erase / destruction certificate workflow, no pentest-tool integration, and no "prohibited tier requires Rules-of-Engagement holder co-sign" pattern.

The combination — engagement-scoped identity + RoE-cosign at prohibited tier + crypto-erase attestation + redaction-aware LLM routing — is not shipped as an integrated system anywhere we can find. That combination is the product. The VMs are an implementation detail of one possible runtime backend.

## Decision

Eidolon v0.1 ships the control plane and nothing else.

In scope for v0.1:

- Scope-token issuance and end-to-end verification
- Engagement lifecycle CLI (open, scope, close, erase, attest)
- Three-tier command gate with operator co-sign at the prohibited tier
- Append-only hash-chained audit log with daily Ed25519-signed rotation
- Hybrid LLM router with sensitivity-classifier-driven redaction
- Certificate of Destruction generation (signed JSON, stub PDF) anchored to audit head hashes
- A `HypervisorBackend` interface defined but with only one stub implementation (no-op / local subprocess)

Out of scope for v0.1:

- The six homelab VMs (Engagement, Logger, Recon, Web, Internal, Wireless). Move to downstream forks.
- Real LUKS volume orchestration and cryptographic erase. v0.1 emits the *attestation* only — the volume itself is BYO.
- Proxmox SDN per-engagement VNETs. BYO networking.
- chattr +a Logger VM with TLS rsyslog. v0.1 uses POSIX append on local disk.
- Multi-engagement concurrency, web UI, REPL.

## Consequences

Good:

- One-week v0.1 ship is realistic. The control plane is bounded; the VM bundle was unbounded.
- Open-source positioning is sharper. "Governance layer for AI-driven offensive work, runtime-agnostic" is defensible and not duplicated elsewhere. "Another Proxmox pentest VM bundle" is duplicated by every homelab on GitHub.
- BYO VM removes adoption friction. Anyone with a Docker host, a Proxmox cluster, a vSphere DC, or just a laptop can adopt Eidolon. They wire their own backend later.
- The hard problems get attention. Operator-identity model, redaction reliability, audit hash chain — these are where Eidolon either succeeds or fails as a product. No engineering oxygen wasted on Packer templates.

Bad:

- "Where do I run my pentest?" question is now the operator's problem, not ours. Mitigation: a `docs/runbooks/byo-vm.md` recipe for the three most common runtimes (Docker, Proxmox, libvirt). Not v0.1 critical path; v0.1 ships with Docker recipe only.
- Demo at v0.1 release requires a runtime to demo against. Mitigation: the dress-rehearsal recording uses the `HypervisorBackend` no-op stub so the demo proves the *control plane* end-to-end without depending on a runtime.
- Some early adopters who wanted "the whole bundle" will be disappointed. Mitigation: ROADMAP shows v0.3 ESXi backend, v0.4 Codex-style sandbox backend, v0.5 Hyper-V + macOS Virtualization.framework backends. The runtime story exists; it just isn't v0.1.

## Alternatives considered

**Ship the full VM bundle in v0.1.** Rejected. Unbounded scope. Not the moat. Reproduces homelab content available everywhere.

**Fork PentAGI and add governance on top.** Rejected. PentAGI's execution layer assumes the agent is authorized to run; Eidolon's entire trust model assumes every action requires per-call authorization bound to an engagement. Refactoring PentAGI to be engagement-scoped is harder than building fresh on the existing FastAPI scope-token + tier-gate code (~150 LOC, already correct).

**Fork Microsoft Agent Governance Toolkit.** Rejected. AGT's governance primitives are closer in spirit, but the engagement-binding is the entire product and AGT has no concept of it. Wrapping AGT to be engagement-scoped is more work than building fresh and inherits AGT's release cadence as a dependency. Cite AGT as prior art in audit-chain and Ed25519-signing ADRs; do not depend on the package.

**Build the control plane in Rust to match the codex-rs sandbox reference.** Rejected for v0.1. Rust would be the right call for a v1.x rewrite of the sandbox-host glue. v0.1 needs to ship in a week. Python + FastAPI + Pydantic + PyJWT is the fastest path to a correct, testable control plane with the people writing it today. Cross-platform sandbox backends (codex-rs windows-sandbox-rs, macOS Virtualization.framework) are scheduled for v0.3+ and may be authored in Rust without disturbing the Python control plane.

## Enforcement

- ROADMAP.md top section states "v0.1 = control plane only, BYO VM" and points here.
- PRD.md out-of-scope lists the six VMs explicitly.
- `vms/` directory is removed from the v0.1 cut. (Empty subdirs deleted; `vms/` itself moves to downstream forks or is deleted entirely.)
- The `HypervisorBackend` interface is defined in v0.1 with a single stub implementation. Real backends are out-of-scope until v0.2.
- Demo dress-rehearsal must run end-to-end against the stub backend. If it can't, v0.1 isn't done.
