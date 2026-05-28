# Runbook — dogfood AD pentest

End-to-end walkthrough of an Eidolon AD recon engagement on Proxmox.
Marked "cut if behind" in the v0.1 plan, but the runbook is shipped so
operators with an AD lab can run it.

## Pre-reqs

- Proxmox VE 8+ host reachable from the orchestrator
- API token configured for the orchestrator
  (`PROXMOX_HOST`, `PROXMOX_USER`, `PROXMOX_TOKEN_NAME`,
  `PROXMOX_TOKEN_VALUE`, `PROXMOX_NODE`)
- VLAN pool: set `PROXMOX_VLAN_POOL_START=1000` and
  `PROXMOX_VLAN_POOL_END=1999` in the orchestrator env
- A pre-built Kali template VM on Proxmox (default id `9000`) with:
  - impacket (`apt install impacket-scripts`)
  - bloodhound-python
  - kerbrute
  - rubeus (binaries dropped)
  - certipy
  - ldapdomaindump
  - netexec / nxc
- An AD lab the operator owns (DC + workstation + a domain user). GOAD
  is the canonical reference setup.

## 0 — orchestrator + login

Same as the web-app runbook (see
[`dogfood-web-app.md`](dogfood-web-app.md)). The orchestrator host
needs the Proxmox env vars set so the substrate can authenticate.

## 1 — store AD credentials

`ad-recon-single` declares two required secrets:
`ad_credentials` (JSON: `{"domain", "username", "password"|"nthash"}`)
and `krb5_conf` (text contents of a krb5.conf for the target domain).

```bash
# Use macOS Keychain or 1Password CLI rather than env if you can.
eidolon secrets store ad_credentials --value \
  '{"domain":"corp.local","username":"jdoe","password":"P@ss"}'
eidolon secrets store krb5_conf --value "$(cat /tmp/krb5.conf)"
```

Verify presence (the broker only confirms the label resolves; values
never come back through the CLI for `ad_credentials` in chat):

```bash
eidolon secrets list
```

## 2 — open + scope

```bash
eidolon engage start --slug ad-dogfood --purpose pentest
eidolon engage scope <ENG_ID> \
  --target 10.10.0.0/16 \
  --permit recon.read \
  --permit recon.fingerprint \
  --tier confirm \
  --ttl 4h
```

Scope tier `confirm` is the right default for AD work — every action
trips a confirm-token requirement, which keeps SPN sweeps and
kerberoasts visible to the operator.

## 3 — provision

```bash
eidolon engage provision <ENG_ID> --template ad-recon-single
```

What happens on the Proxmox side:
- VLAN allocated from the pool, attached to a `vmbr` on the host.
- Kali template (id 9000) cloned. The clone gets an interface on the
  allocated VLAN, `EIDOLON_VM_TOKEN` injected via cloud-init.
- The orchestrator records the VMHandle and audits
  `substrate_vm_provisioned`.
- `secrets_inject` mounts `ad_credentials` and `krb5_conf` under
  `/run/eidolon-secrets/` inside the cloned VM.

```bash
eidolon engage vms <ENG_ID>     # confirm address + handle
```

## 4 — drive from Claude Code

> "Run AD recon against `corp.local` from engagement `<ENG_ID>`,
> ad-recon-single template. Start with passive recon (DNS, anonymous
> LDAP, port 389/636). Fire `mode_change` before AS-REP roast or
> kerberoast. Fire `cred_disposition` if you recover any hashes
> before storing or relaying. Hard stop at scope edge."

The fork policies in `ad-recon-single/template.yaml` require operator
approval for every transition — this is intentional for AD work.

## 5 — close + verify + erase

```bash
eidolon engage close <ENG_ID>      # revoke scope tokens, keep VMs
eidolon engage erase <ENG_ID>      # close + Proxmox VM destroy + VLAN release
eidolon audit verify
```

Verify the VLAN was released back to the pool by inspecting Proxmox
network config or rerunning `engage provision` for a new engagement —
the VLAN id should differ.

## v0.1 known limits

- `secrets_inject` is wired into `ProxmoxSubstrate` but only as a
  best-effort: the cloud-init payload includes the secret files; if
  cloud-init isn't enabled in the template, secrets are not injected.
  Workaround: enable cloud-init on the Kali template VM, or copy
  secrets manually after provision.
- `kerbrute` and `rubeus` paths are not validated by the bootstrap
  script. If you customize the template image, add a healthcheck.
- VLAN exhaustion (1000 used) returns `503 vlan_pool_exhausted` from
  provision. Bump `PROXMOX_VLAN_POOL_END`.

## What to capture

For the dogfood pass, log:

| Question | Pass? | Friction |
|----------|-------|----------|
| VLAN cleanly allocated and tagged | y/n | |
| Cloud-init injected `EIDOLON_VM_TOKEN` | y/n | |
| AI fired `mode_change` before active probes | y/n | |
| `cred_disposition` fired on recovered hash | y/n | |
| Workspace `findings/` had structured AD findings | y/n | |
| `engage erase` released VLAN + destroyed VM | y/n | |
| `audit verify` clean post-close | y/n | |

This is a v0.1.1 release-candidate gate. A clean pass justifies
shipping the AD template; a noisy pass means we hold ad-recon-single
back to v0.1.1.
