# Security policy

## Reporting a vulnerability

Do not open a public GitHub issue for a security vulnerability in Eidolon.

To report:

1. Open a private security advisory at the repo's [Security tab](https://github.com/amir-hosseinpour/eidolon/security/advisories/new). Do not email or open a public issue.
2. Include:
   - A description of the vulnerability.
   - Steps to reproduce.
   - Impact. What can an attacker do?
   - Any suggested mitigation.
3. Expect acknowledgment within 72 hours.
4. Expect a fix timeline: 14 days for critical, 30 days for high, 90 days for medium.

## Scope

The policy covers vulnerabilities in:

- The Eidolon orchestrator, CLI, and agent definitions.
- The VM provisioning scripts (`vms/*/provision`).
- The scope token HMAC validation and command tier enforcement.
- The audit log shipping path (operator to logger VM).
- The LiteLLM router configuration templates.

Out of scope:

- Upstream tools (hashcat, nmap, burp, metasploit, sliver). Report those upstream.
- Third party AI providers (Google Gemini, local model quantization bugs).
- Operator misconfiguration (for example, running Eidolon on an unpatched host).
- Firm grade concerns (client isolation, signed logs, Certificate of Destruction). Those live in forks (Voyageur). Report fork specific issues to the fork maintainer.

## Our commitments

We acknowledge valid reports publicly after the fix ships, unless the reporter wants to stay anonymous.

We coordinate disclosure timing with the reporter.

We do not pursue legal action against good faith security researchers who follow this policy.

## Security critical components

These paths get enhanced review:

- Anything under `orchestrator/agents/` (agent tool scoping)
- `vms/sandbox/` (session workspace lifecycle)
- `vms/logger/` (append only audit log integrity)
- Scope token HMAC validation
- Command tier enforcement (autonomous / confirm / prohibited)
- Egress firewall rule generation

Contributing to any of these? Expect multi maintainer review and a longer merge timeline.

## Threat model

See [`docs/architecture/threat-model.md`](docs/architecture/threat-model.md).

At a high level, Eidolon defends against:

- Scope escalation by an AI agent, via HMAC signed scope tokens validated at every FastAPI boundary.
- Out of scope network activity from the recon VM, via per session egress filters.
- Accidental writes from an agent outside the active session workspace.
- Operator workstation compromise of session artifacts, by keeping artifacts on the sandbox VM.

Eidolon does not defend against:

- A malicious Proxmox host administrator.
- An attacker who already owns the operator's Claude Code session with full workstation access.
- Supply chain attacks on upstream tools (hashcat, etc.).
- Flawed operator OPSEC (shared passwords, secrets in git).
- Cross client data separation. Eidolon runs one session at a time. Forks (Voyageur) carry that defense.
- Forensic recovery from disk. Eidolon does not do cryptographic erase. Forks (Voyageur) carry that.
