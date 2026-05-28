# Contributing to Eidolon

Eidolon is a security sensitive project. Contributions are welcome, but the review bar is higher than a typical open source repo. A bug in scope enforcement lets an agent touch something it should not. That is the constraint we care about.

## Before you start

1. Read [`PRD.md`](PRD.md) and [`docs/architecture/overview.md`](docs/architecture/overview.md).
2. Read the ADRs in [`docs/adr/`](docs/adr/). Many design choices are intentionally constrained.
3. Open an issue before starting significant work. Large PRs with no prior discussion usually get rejected.

## Ground rules

All commits must be GPG signed. `git commit -S`. Unsigned commits do not get merged.

Do not introduce a dependency on any single AI provider in the runtime path. See ADR 0002.

Do not weaken scope enforcement (scope tokens, command tier gating, egress filters) without a matching ADR.

Security sensitive changes (anything under `orchestrator/`, `vms/*/security/`, or touching scope token or command tier logic) need review from a maintainer with a track record on the project.

No GPL code in the runtime path. GPL inside target VMs for tools (Kali included) is fine. GPL in the orchestrator or router is not.

Do not add firm grade features (client isolation, signed Certificate of Destruction, multi session concurrency, engagement memory, compliance mappings) to Eidolon. Those belong in forks. Downstream forks carry these.

## Development setup

Coming with v0.1. In the meantime:

```bash
git clone git@github.com:<you>/eidolon.git
cd eidolon

# Spin up a dev Proxmox or use a shared lab
# ...
```

## Pull request process

1. Fork the repo.
2. Topic branch: `feat/short-description` or `fix/short-description`.
3. Write tests for new code in security sensitive paths. No exceptions.
4. Update docs when changing user facing behavior.
5. Architecture change? Add an ADR in `docs/adr/` in the same PR.
6. PR against `main`.
7. Fill out the PR template (coming in v0.1).
8. Expect 1 or 2 rounds of review. Security sensitive PRs take longer.

## Commit style

Imperative mood. "Add scope token rotation", not "Added scope token rotation".

Reference the issue: `Closes #123` or `Refs #123`.

Keep commits atomic. Squash cosmetic fixups before review.

## Reporting bugs

Non security bugs: open a GitHub issue with the `bug` label.

Security vulnerabilities: see [`SECURITY.md`](SECURITY.md). Do not open a public issue for a security bug.

## Code of conduct

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Eidolon runs under the Contributor Covenant.

## Licensing of contributions

Submitting a PR means your contribution lands under the same MIT license as the rest of the project.

## Fork policy

Eidolon is built to be forked. Firm specific downstream forks are expected and welcome. They do not need to publish their changes. You are not required to contribute back. Upstream improvements to shared components (orchestrator, scope token logic, LiteLLM router config) are still welcome.
