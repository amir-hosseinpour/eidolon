# Eidolon, threat model

Status: Draft
Last updated: 2026-04-20

## Scope of this model

What Eidolon is trying to protect, who it assumes attacks it, and what lives outside its defenses.

Eidolon is a framework for a single operator on a trusted Proxmox host. Firm grade threat models (multi client isolation, forensic grade audit, chain of custody) belong to forks like Voyageur and are not in scope here.

## Assets

Ranked by blast radius.

1. Session artifacts. Hashes cracked, tool output, notes, screenshots captured during the session.
2. Session scope. The set of targets the operator authorized the session to touch.
3. Audit logs. Record of what the operator and agents did during the session.
4. Operator identity material. Signing keys, WireGuard keys, scope token HMAC secret.
5. Upstream model API keys (Gemini, any other commercial provider).
6. Infrastructure state (Proxmox creds, firewall rules).

## Trust boundaries

Operator laptop. Runs Claude Code on a consumer Anthropic sub. Trusted for session interaction.

Orchestrator VM. Trusted for scope validation and session lifecycle. The blast radius if compromised is the open session plus any cached credentials in orchestrator memory.

Per VM job servers. Trusted for the role they implement. Each validates the scope token before acting.

Logger VM. Append only. Trusted receive only.

LiteLLM router. Trusted for routing and cost tracking.

Outbound third parties (Gemini, Google Cloud). Untrusted. Operator is responsible for not sending data that shouldn't leave the premises.

## Attackers

| Attacker | Goal | Capability |
|----------|------|------------|
| External network attacker | Pivot into target networks via Eidolon | Port scan, internet side exploit, credential stuffing |
| Malicious target | Pivot back through Eidolon into the operator's home network | Send crafted responses, try reverse shells |
| Compromised operator laptop (malware) | Read session state, exfil artifacts | Full laptop access while operator is logged in |
| Upstream model provider | Train on or retain data sent to them | Receives prompts from Eidolon |
| Supply chain | Backdoor hashcat, nmap, rsyslog | Ships a malicious update |

## Defenses by attacker

External network attacker. Host firewall. Operator to host via WireGuard plus mTLS. No inbound from the internet except the listener VM's declared C2 endpoints (v0.2+).

Malicious target. Scope token bound to in scope IPs and CIDRs. Out of scope actions hard refused at the orchestrator. Listener VM runs in its own VNET.

Compromised operator laptop. Session artifacts stay on the sandbox VM. The laptop holds session state only. FileVault required. Hardware keys (YubiKey for GPG, TouchID for WireGuard unlock) where the operator can run them.

Upstream model provider. Operator controls what gets routed to commercial models via the LiteLLM config. Sessions that disallow egress route everything to the LLM Analyst VM and never touch a commercial endpoint. No automatic redaction layer ships in v0.1; that lands in Voyageur.

Supply chain. Pin dependency versions. Use signed releases where available. Monitor security advisories. Not a full defense.

## Out of scope threats

These are real threats that Eidolon does not defend against. Forks that care about them (Voyageur) carry the defense.

- Multi client data separation. Eidolon runs one session at a time. Cross client leakage is not a scenario the framework considers.
- Forensic grade audit. Eidolon logs are plain rsyslog over TLS. No GPG signing, no external append only mirror, no chain of custody artifact.
- Post session data destruction. Eidolon does not do cryptographic erase or signed Certificate of Destruction.
- Insider at the Proxmox host. The framework is single operator and assumes the operator controls the hypervisor.
- Regulatory compliance (PIPEDA, GDPR, SOC 2, PCI DSS, CREST). Eidolon is not a compliance product.

## Attack surface by layer

Network. WireGuard to host (one port), Proxmox web UI (SSH tunnel only, no public), listener VM public endpoints (v0.2+).

Orchestrator. FastAPI. Scope token HMAC. Rate limiting. Every endpoint authenticated.

Per VM servers. Only reachable from the orchestrator over the mgmt VNET. Not reachable from target VNETs.

LiteLLM. Only reachable from the orchestrator. Not reachable from target VNETs.

Logger. Only reachable from orchestrator and VM job servers for writes. Reads through the orchestrator only.

## Known residual risks

Live session compromise. If the orchestrator gets rooted while a session is open, cached credentials are readable from RAM.

Operator OPSEC. Reuse of shared passwords, secrets in git, bad SSH hygiene. Not solvable in software.

Zero days in upstream tools. Hashcat, rsyslog, nmap. Pin versions and monitor.

Side channels on shared hardware. Arc A380 on the same host as the cracker RX 7600 XT. PCIe passthrough isolates the card but not the PCIe root complex. Accept for v0.1.

## Related

- [`../../SECURITY.md`](../../SECURITY.md)
