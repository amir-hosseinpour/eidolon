# Eidolon v0.1 Blueprint

Status: Active blueprint. Supersedes `docs/BUILD-PLAN-V0.1.md` (which framed the
project as a compliance/governance tool — wrong framing, see below).

Audience: me (Damion) building it, plus future contributors.

## What Eidolon actually is

A templated multi-VM workspace orchestrator for AI-driven offsec engagements.

The problem it solves: when an AI agent runs a pentest, its context gets polluted
across long-running engagements. The same Claude Code session that recons a web
app on Tuesday and pivots to AD on Wednesday will hallucinate, mix details, leak
context between engagements. The fix is **isolation**: each engagement is its
own workspace with its own VMs, its own scope, its own AI memory, its own
secrets, its own audit trail. When you close the engagement, everything goes
away cleanly (or gets archived if you opt in).

The second problem: existing AI agent permission systems (Anthropic's `--dangerously-skip-permissions`
flag, Cloud's per-tool prompts) are either off or in your face every two seconds.
Eidolon does **decision-gating only at strategic forks** — five fixed fork types
that fire when the AI hits a moment that actually matters (path selection, mode
change, credential disposition, noise threshold, scope edge). Everything else is
auto.

This is not a compliance tool. It's not a governance dashboard. It's a workspace
orchestrator that lets a real pentester (me) drive AI agents through real
engagements without losing my mind to context pollution or permission spam.

The compliance/governance flavor (Cert of Destruction, operator co-sign, SOC 2
audit trail) belongs in **downstream forks**. Not
covered here.

## Architecture overview

```
+-------------------+ Tailscale / LAN +----------------------+
| Operator laptop | <------ bearer token ----------> | Orchestrator host |
| (macOS, CC + skills) + MCP | (Proxmox VM, |
| | | Linux/Docker, etc.) |
| ~/.eidolon/ | |
| laptop.yaml | | $EIDOLON_HOME/ |
| ~/.claude/skills/ | | state.db (SQLite) |
| eidolon/ | | audit/ |
| | | engagements/<id>/ |
+-------------------+ | templates/ |
 | secrets/ |
 +----------------------+
 |
 | substrate driver
 v
 +----------------------+
 | VMs / containers |
 | (Proxmox or Docker) |
 | each runs eidolon- |
 | agent for identity + |
 | secret broker proxy |
 +----------------------+
```

Components, in plain words:

- **Orchestrator** — FastAPI app on the host. Owns engagements, scope tokens,
 audit log, fork stream, secrets broker, substrate calls. SQLite for state.
- **MCP server** — wraps the orchestrator's REST surface as MCP tools so any
 MCP-aware AI client can use it. Lives next to the orchestrator on the host.
- **Laptop CLI + skills** — `eidolon` CLI plus three Claude Code skills that
 give CC ergonomic wrappers over the MCP layer.
- **Substrate drivers** — `ProxmoxSubstrate`, `DockerSubstrate`. Each implements
 a small ABC: `provision`, `snapshot`, `destroy`, `network_create`, etc.
- **Templates** — directory-per-template with `template.yaml`, `scripts/`,
 `skills/`, `workspace_skeleton/`, `README.md`. Three ship in v0.1:
 `blank-kali`, `web-app-pentest`, `ad-recon-single`.
- **VM agent** — small Python daemon `eidolon-agent` baked into template VMs.
 Registers VM identity at boot, exposes localhost socket for in-VM tools to
 request secrets. Heartbeats to orchestrator.

## Decision-fork model

Five fixed fork types. Hardcoded enum in `eidolon/orchestrator/lib/forks.py`.
Adding a new type is a code change, not config — keeps discipline.

| Type | Triggered by | Why it exists |
|---|---|---|
| `scope_edge` | Orchestrator (CIDR check on every dispatch) | Hard safety floor. AI cannot bypass. |
| `cred_disposition` | Orchestrator (high-sensitivity secret access) | Hard safety floor. Operator confirms before secret leaves broker. |
| `path_selection` | AI judgment (skill prompt) | "Two paths forward, which one." Strategic moment, not safety. |
| `mode_change` | AI judgment (skill prompt) | Going from passive to noisy, or recon to exploit. |
| `noise_threshold` | AI judgment (skill prompt) | Scanner about to touch many hosts; operator may want to throttle. |

Hybrid trigger model: orchestrator hard-enforces the two safety types,
AI judgment fires the three strategic types via skill prompts.

UX: AI calls `POST /forks` (via MCP), gets `fork_id`. Operator's CC has
`eidolon-fork-watcher` skill subscribed to `GET /forks/stream` (SSE). New fork
pops into operator's CC chat as a regular message. Operator says "approve
option 2" or "deny because X" — skill translates to `POST /forks/{id}/resolve`.

Both creation and resolution land in the audit chain.

## Repo layout (v0.1 target)

```
eidolon/
 cli/
 main.py # operator-facing CLI
 orchestrator.py # host-side: init, start, rotate-token
 skills_install.py # writes ~/.claude/skills/eidolon/
 orchestrator/
 app/
 main.py # FastAPI app factory
 dependencies.py # bearer auth + DB session injection
 routers/
 engagements.py
 tools.py # dispatch (kept from Spec 002)
 forks.py # NEW: SSE stream + resolve
 secrets.py # NEW: broker REST
 templates.py # NEW: list/info templates
 workspace.py # NEW: read/append/replace engagement MD
 health.py
 # authorizations.py REMOVED (operator cosign moved to downstream forks)
 lib/
 audit.py # KEEP (Spec 004)
 scope.py # KEEP (Spec 001)
 engagements.py # KEEP, strip cert generation
 revocation.py # KEEP
 config.py # KEEP
 keys.py # KEEP (JWT scope-token signing key)
 state.py # NEW: SQLite layer (SQLAlchemy or stdlib)
 forks.py # NEW: 5 fork types + lifecycle
 templates.py # NEW: template loader + validator
 workspace.py # NEW: engagement workspace MD I/O
 secrets/
 __init__.py
 broker.py # NEW: scope tuple matching, audit hooks
 keychain.py # NEW: macOS Keychain driver
 onepassword.py # NEW: 1Password CLI driver
 substrate/
 __init__.py
 base.py # NEW: ABC
 proxmox.py # NEW: pvesh / proxmoxer driver
 docker.py # NEW: docker-py driver
 # mac.py + windows.py = stubs raising NotImplementedError("v0.2")
 # cert_of_destruction.py REMOVED (downstream forks)
 # operators.py REMOVED (downstream forks)
 mcp_servers/
 __init__.py
 server.py # NEW: MCP server wrapping REST surface
 tools/ # NEW: one file per MCP tool group
 agents/ # KEEP existing markdown stubs as starter docs
templates/
 blank-kali/ # NEW
 template.yaml
 scripts/provision.sh
 workspace_skeleton/
 README.md
 web-app-pentest/ # NEW
 template.yaml
 scripts/{provision_kali.sh, juice_shop_compose.yaml}
 skills/web-app-recon/
 workspace_skeleton/
 README.md
 ad-recon-single/ # NEW (Proxmox-only)
 template.yaml
 scripts/{provision_dc.sh, provision_kali.sh, ad_seed.ps1}
 skills/ad-recon/
 workspace_skeleton/
 README.md
 # engagement-template/ EMPTY DIR REMOVED
vm_agent/ # NEW: separate Python package
 eidolon_agent/
 __init__.py
 main.py # boots, registers identity, broker proxy
 config.py
 pyproject.toml
docs/
 BLUEPRINT-V0.1.md # this file
 concepts.md # NEW: workspace, fork, substrate, broker
 templates.md # NEW: how to write templates
 decision-forks.md # NEW: 5 types deep dive
 api.md # NEW: REST + MCP tool reference
 constitution.md # KEEP
 BUILD-PLAN-V0.1.md # MARK SUPERSEDED, link to this file
 specs/
 001-scope-token-end-to-end/ # KEEP, polish notes
 002-engagement-lifecycle-cli/ # KEEP, mark cert section moved-to-downstream forks
 003-three-tier-command-gate/ # KEEP, mark cosign section moved-to-downstream forks
 004-audit-log-hash-chain/ # KEEP unchanged
 005-hybrid-llm-router-with-redaction/ # MARK deferred to v0.2
 006-substrate-and-templates/ # NEW spec doc
 007-decision-forks/ # NEW spec doc
 008-secrets-broker/ # NEW spec doc
 009-mcp-server/ # NEW spec doc
tests/
 test_audit_chain.py # KEEP
 test_audit_cli.py # KEEP
 test_scope_token.py # KEEP
 test_engagement_*.py # KEEP, drop cert/cosign assertions
 test_state_db.py # NEW
 test_forks.py # NEW
 test_substrate_docker.py # NEW (uses real Docker, marked integration)
 test_substrate_proxmox.py # NEW (mocked or skipped without env)
 test_secrets_keychain.py # NEW (skipped on non-macOS)
 test_templates_loader.py # NEW
 test_workspace.py # NEW
 test_mcp_server.py # NEW
```

## Existing-code triage (final)

| Path | Verdict |
|---|---|
| `eidolon/orchestrator/lib/audit.py` | **Keep**. Spec 004 work, complete. |
| `eidolon/orchestrator/lib/scope.py` | **Keep**. Spec 001 work, polish. |
| `eidolon/orchestrator/lib/engagements.py` | **Keep**. Strip cert generation in `engagement_erase`; defer to substrate destroy + workspace archive. |
| `eidolon/orchestrator/lib/cert_of_destruction.py` | **Move to downstream forks** before v0.1 ship. |
| `eidolon/orchestrator/lib/operators.py` | **Move to downstream forks**. Operator Ed25519 co-sign is compliance feature. |
| `eidolon/orchestrator/lib/revocation.py` | **Keep**. Scope token revocation is core. |
| `eidolon/orchestrator/lib/keys.py` | **Keep**. JWT signing key for scope tokens. |
| `eidolon/orchestrator/lib/config.py` | **Keep**. |
| `eidolon/orchestrator/app/routers/authorizations.py` | **Move to downstream forks**. Operator co-sign endpoints. |
| `eidolon/orchestrator/app/routers/engagements.py` | **Keep**. Drop cert response from `/erase`, drop authz endpoints. |
| `eidolon/orchestrator/app/routers/tools.py` | **Keep**. Dispatch + tier gate stays. |
| `eidolon/cli/main.py` | **Keep**. Drop `authz` group. Add `engage`, `fork`, `secrets`, `templates`, `orchestrator` groups. |
| `templates/engagement-template/` | **Delete**. Empty dir, replace with three real templates. |
| `eidolon/orchestrator/agents/*.md` | **Keep as docs**. Future v0.2 agents can grow from these stubs, but don't ship as agents in v0.1 (skills are enough). |
| `docs/BUILD-PLAN-V0.1.md` | **Mark superseded**. Add header link to BLUEPRINT-V0.1.md. Don't delete (history). |
| `docs/specs/005-hybrid-llm-router-with-redaction/` | **Mark deferred to v0.2**. |

## Three-tier gate vs fork types — clarification

These are different concepts, both stay in v0.1. Spec 003's tier (`autonomous` /
`confirm` / `prohibited`) is the *gating mode* attached to a scope token: how
strict is the orchestrator about this scope. Fork types are the *shape of the
decision* when a gate fires. A `confirm`-tier scope can fire a `path_selection`
fork OR a `noise_threshold` fork OR `scope_edge`, etc.

Concretely:
- Tier on scope token = "what level of human approval is required for actions in this scope"
- Fork type on a fork instance = "what category of decision is being asked"

Both land in audit. Both observable from CLI. Don't conflate.

## v0.1 day-count plan

Realistic per-day estimate based on me-with-AI productivity. Reverse-engineered
from "ship before v0.1 release — real bar is
dogfooding for a real engagement." Rough order ≈ dependency order.

| Days | Task |
|---|---|
| 1 | downstream forks extraction: move cert, operators, authz endpoints; delete tests; verify CI green |
| 2 | SQLite state layer: schema, migrations, replace `EngagementStore`/`ScopeTokenStore`/`DispatchStore` with DB-backed |
| 1 | Bearer token middleware: `Authorization: Bearer` on all routes except `/health`; `eidolon orchestrator init` generates token |
| 2 | Substrate ABC + DockerSubstrate: provision, snapshot, destroy, network_create. Docker network = engagement isolation. |
| 3 | ProxmoxSubstrate: VM clone, snapshot, VLAN tag, destroy via `proxmoxer`. Real Proxmox required for tests. |
| 1 | Substrate stubs (Mac, Windows): `NotImplementedError("v0.2")` plus roadmap note in docs |
| 2 | Templates loader + validator: `template.yaml` schema, directory walker, error messages |
| 1 | `blank-kali` template (whichever substrate happens) |
| 2 | `web-app-pentest` template (Docker primary, Proxmox optional) |
| 3 | `ad-recon-single` template (Proxmox only — DC + workstation + Kali, AD seed PowerShell) |
| 2 | Workspace MD layer: `workspace_skeleton` materialization, append/replace API, ~10KB summarize threshold |
| 2 | Forks lib: 5-type enum, lifecycle, CIDR check for `scope_edge`, secret-sensitivity hook for `cred_disposition` |
| 2 | Forks SSE endpoint + REST CRUD; integration test with fake EventSource client |
| 2 | Secrets broker: scope tuple, Keychain driver (macOS host or Linux fallback `pass`), audit hooks |
| 1 | 1Password CLI driver |
| 2 | VM agent: Python daemon, identity registration via `EIDOLON_VM_TOKEN`, localhost socket for in-VM tools |
| 3 | MCP server: REST → MCP tool wrapping; one tool group per resource (engagements, forks, secrets, workspace, templates); auth via bearer |
| 2 | Laptop skills: `eidolon-core.md`, `eidolon-fork-watcher` (SSE subscriber), `eidolon-engagement` (NL wrapper) |
| 1 | `eidolon login` flow: write `~/.eidolon/laptop.yaml`, register MCP server in CC config |
| 1 | `eidolon orchestrator init/start/rotate-token` host-side commands |
| 1 | CLI rewrite: `engage start/list/show/close/workspace-edit`, `fork list/resolve`, `templates list/info`, `secrets store/get/list/revoke` |
| 2 | docs: README quickstart, concepts, templates, decision-forks, api |
| 2 | Dogfood: run a real web-app engagement against own juice-shop, take screenshots/video for talk |
| 2 | Dogfood: run a real AD engagement against own AD lab |
| 2 | Bug fix + polish from dogfood pass |

**Total: ~41 days of work.** Calendar = ~5 weeks ≈ 35 working days for me.
**Implication: 6 days over.** First cuts if behind: `ad-recon-single` template
(slip to v0.1.1) and 1Password driver (Keychain only v0.1).
That trims 5 days. Second cut: defer dogfood-AD pass, demo only web-app workflow.

## Success bar (dogfood, not demo)

I should be able to run a real client web-app pentest entirely through Eidolon:
- `eidolon engage start web-app-pentest --slug <client-name> --scope <CIDRs>` → workspace exists, VMs alive, scope token issued
- AI does recon, fires `noise_threshold` fork before SQLMap, I approve in CC
- AI hits scope edge attempting to scan parent network, orchestrator hard-blocks, I deny
- I edit `notes.md` directly with my own observations
- 8 hours later, AI summarizes findings into `findings.md` from notes
- `eidolon engage close <id>` (default archive) → VMs nuked, secrets revoked,
 audit log clean, snapshot tar at `$EIDOLON_HOME/engagements/<id>/`
- `eidolon audit verify` clean
- I can come back two weeks later, unarchive, re-test with new scope token

If that flow works on a real engagement (not just a demo target), v0.1 is done.

## v0.2 roadmap (not committed dates)

- Mac substrate (Lima or Tart)
- Windows substrate (Hyper-V or WSL2)
- Bundled agents (recon-agent, redteam-agent) on top of skills
- Hybrid LLM router with PII/secrets redaction (Spec 005)
- Additional templates: drone-pentest, ad-recon-concurrent, cloud-recon
- TUI dashboard for engagement status (textual)

## Open questions deferred to implementation time

- SQLAlchemy vs stdlib `sqlite3`: lean stdlib unless ORM helps; revisit if joins
 get painful.
- MCP server framework: `mcp` reference SDK vs hand-rolled. Probably reference
 SDK; check for FastAPI integration story.
- Secrets broker on Linux orchestrator host: `pass` (gpg) is simplest, Secret
 Service requires D-Bus session.
- Fork SSE keepalive interval: probably 15s, tune if reverse proxies kill idle.
- Template validator strictness: schema-strict in v0.1, permit unknown keys for
 forward compat? Lean strict-with-clear-error-messages.
