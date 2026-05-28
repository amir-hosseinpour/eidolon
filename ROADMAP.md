# Eidolon, roadmap

Status: Draft
Last updated: 2026-04-26

## v0.1 = control plane only (BYO VM)

v0.1 ships the governance layer for AI-driven offensive security work. Zero VMs. Operators wire their own runtime via the `HypervisorBackend` interface. Rationale: ADR 0008. The six homelab VMs originally planned for v0.1 (Engagement, Logger, Recon, Web, Internal, Wireless) move to Voyageur and to v0.2+ reference backends.

## Release cadence

Semantic versioning, lightweight cycle.

v0.x. Alpha. Not production ready. Breaking changes expected.
v1.0. Stable engagement lifecycle and governance surface. Safe for independent pentesters and researchers running their own work.
v2.0. Paperclip orchestrator research surface. Autonomous agent loops as a first-class option.

## v0.1 MVP (target: DefCon Toronto, May 2026)

Theme: control plane end-to-end against a no-op runtime backend. One engagement, one operator, every governance primitive proven.

- [ ] Pre-flight: package layout fixed, `make verify` green, CI workflow on push/PR (P-1..P-4)
- [ ] `docs/constitution.md` distilling the ADRs into enforceable rules (P-5)
- [ ] ADR-0008 control-plane-only scope cut (this doc) (P-6 — DONE)
- [ ] PRD + ROADMAP reflect scope cut (P-7 — this commit)
- [ ] Spec 001: scope-token-end-to-end (issuance + per-tool verification + expiry + revocation)
- [ ] Spec 002: engagement-lifecycle CLI (open / scope / close / erase / show + Cert of Destruction emission)
- [ ] Spec 003: three-tier command gate with operator co-sign at the prohibited tier
- [ ] Spec 004: append-only hash-chained audit log with daily Ed25519-signed rotation
- [ ] Spec 005: hybrid LLM router with sensitivity-classifier-driven redaction + `--strict-local` flag
- [ ] `HypervisorBackend` interface defined; `NoOpBackend` stub implemented and used in tests
- [ ] BYO Docker recipe in `docs/runbooks/byo-docker.md`
- [ ] End-to-end smoke test (`tests/test_end_to_end_engagement.py`, 8 steps)
- [ ] DefCon Toronto demo dress-rehearsal recording (5 min, against `NoOpBackend`)
- [ ] Tag `v0.1.0` with release notes citing PentAGI and Microsoft AGT as adjacent prior art

Exit criteria: `make verify` passes, end-to-end smoke test passes, demo dress-rehearsal recording exists, release notes published.

## v0.2 reference runtime backends (target: post v0.1)

- [ ] Proxmox backend (the original homelab path, now as a backend implementation)
- [ ] Docker Compose reference recipe upgraded to a first-class backend
- [ ] LiteLLM observability (Langfuse integration, per-engagement cost report)
- [ ] CTF mode engagement template
- [ ] Tools router catalog: nmap / nuclei / burp wrappers behind the tier gate

## v1.0 stable (target: plus 6 to 8 weeks after v0.2)

- [ ] Operator handbook (`docs/handbook.md`)
- [ ] Public security audit. Invite 1 to 2 independent reviewers.
- [ ] Packaged installer (Ansible playbook or Terraform module) for a fresh Proxmox host
- [ ] Upgrade runbook from v0.x to v1.0
- [ ] 90 day support commitment on the v1.0 branch

Exit criteria: 500 GitHub stars or 3 known production forks (Voyageur counts as one), whichever comes first.

## v2.0 Paperclip orchestrator (research phase)

Theme: autonomous offensive agent loops with human gates.

See [`docs/future/paperclip-orchestrator.md`](docs/future/paperclip-orchestrator.md) for the full spec. Summary:

- Fork the Paperclip agent orchestration pattern (from the personal homelab base)
- Pluggable LLM backend (local or API)
- Autonomous recon plus tool dispatch with human approval gates at each command tier
- Auto drafted session notes and summary
- Safety rails: token budget, action budget, deadman timer, loop detection

Not planned for v1.0. Research and prototype in a long lived branch.

## Cross-hypervisor and cross-host backends (v0.3+)

Theme: the `HypervisorBackend` interface is defined in v0.1 with one stub. Reference backends ship in v0.2 (Proxmox + Docker), then portability widens.

- [ ] v0.3 ESXi backend. pyVmomi plus NSX or vSwitch port groups for L2 isolation. Guest-side LUKS still works for crypto erase. Highest enterprise pull.
- [ ] v0.4 Sandbox backend. Process-tree isolation, no VM. Linux seccomp plus namespaces, macOS `sandbox-exec`, Windows AppContainer plus Job Object (see [openai/codex windows-sandbox-rs](https://github.com/openai/codex/tree/main/codex-rs/windows-sandbox-rs) for the Windows pattern). Same scope tokens, same command-tier gate, weaker isolation. Solo operator and demo mode.
- [ ] v0.5 Hyper-V backend on Windows hosts. PowerShell plus WMI lifecycle, Hyper-V vSwitch isolation, BitLocker for crypto erase.
- [ ] v0.5 macOS Virtualization.framework backend. Native APFS volumes per engagement, vmnet for isolation. Hardest port (newer API, less library coverage).

Non-goal: feature parity across all backends in one release. Backends ship sequentially with their own exit criteria.

## Longer horizon (unscheduled)

Eidolon Blue. Sibling project for blue team tabletops on the same infrastructure.

Distributed cracker. Hashtopolis style multi node cracking.

OWASP Top 10 target library. Drop in vulnerable apps for training.

Mobile app pentest VM. Emulator plus Frida plus Burp mobile.

Cloud pentest VMs. AWS/Azure/GCP lab provisioning (post v1, Proxmox native guarantee stays).

GUI operator console. Electron or Tauri app as an alternative to Claude Code.

## Non goals (explicit)

Eidolon core will not ship the following, regardless of community demand.

No closed-source components.
No mandatory telemetry to any third-party service.
No integration that requires a SaaS signup to use Eidolon.
No hard dependency on any single AI provider at runtime.
No managed VM provisioning in Eidolon core. Voyageur ships managed runtime as a commercial offering.
No client-engagement platform features beyond what governance demands. Multi-engagement concurrency, engagement memory, compliance mappings, branded reports belong to forks. **The Cert of Destruction attestation IS in scope** (signed JSON anchored to audit head hashes); the LUKS volume orchestration backing it is BYO or Voyageur.

See [`PRD.md`](PRD.md) for product requirements. Each release gets a tagged milestone with tracked issues.
