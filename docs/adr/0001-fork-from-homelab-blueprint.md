# ADR 0001: Fork from the personal homelab blueprint

Status: Accepted
Date: 2026-04-18

## Context

Eidolon started as a fork of a personal Proxmox homelab scaffold that already ran day to day for home use. The homelab shipped with gaming VMs, a personal media stack, and a generic AI assistant. None of that belongs in a pentest framework.

Two concerns at the fork point:

1. Should Eidolon start from scratch, or keep the homelab provisioning, networking, and observability as a base?
2. How does Eidolon relate to firm specific forks (the canonical one is Voyageur for White Tuque)?

## Decision

Fork the homelab blueprint. Strip all personal and gaming components. Keep the Proxmox, SDN, monitoring, and tooling scaffolds. Make Eidolon open source under MIT. Treat firm forks (Voyageur) as downstream, proprietary, and free to diverge.

Eidolon is the upstream. Voyageur is the downstream, tied to White Tuque. The relationship matches VS Code and Cursor. One open, one proprietary on top.

## Consequences

Good:

- Months of proven provisioning work transfers directly. SDN, monitoring, GPU handling, secrets layout.
- Any operator with a homelab mindset can grok Eidolon quickly.
- Firms that want proprietary tweaks (intake forms, branded reports, CTI feeds) fork Voyageur or roll their own without Eidolon core needing to care.

Bad:

- We inherit some defaults that made sense for gaming or personal use. They need careful scrubbing. Touched in the fork scrub pass.
- Two repos to maintain. Eidolon must keep a clean API for forks to rebase on.

## What stays vs. what gets stripped

Stays: Proxmox base, SDN provisioning, Docker for auxiliary services, Grafana for observability, secrets layout, ZFS pool layout.

Stripped: SteamOS or gaming VMs. Xbox streaming. Emulator VMs. Personal media stacks. Any assistant preset that is not pentest focused.

## Alternatives considered

Start from scratch. Rejected. Six weeks of undifferentiated work rewriting proven provisioning.

Keep gaming VMs as optional profiles. Rejected. Eidolon is work only. Mixing gaming images and security work surfaces invites the operator to run them on the same Proxmox host. That's a data hygiene foot gun.

Upstream to the personal homelab. Rejected. The personal project is scoped to one operator's life and has different tradeoffs.
