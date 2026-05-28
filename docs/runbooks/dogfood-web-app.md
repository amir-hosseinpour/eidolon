# Runbook — dogfood web-app pentest

End-to-end walkthrough of an Eidolon web-app pentest against a local
Juice Shop instance. This is the v0.1 success-bar runbook. If this
flow fails on real targets, v0.1 is not done.

## Pre-reqs

- macOS or Linux laptop with Python 3.13+
- Docker Desktop running (for `docker` substrate provisioning)
- A clone of `eidolon` with `pip install -e ".[dev]"` complete
- A Juice Shop instance reachable from the engagement network. Easiest:
  ```bash
  docker network create eidolon-targets
  docker run -d --name juice-shop --network eidolon-targets \
    -p 3000:3000 bkimminich/juice-shop
  ```
  Note the IP: `docker inspect -f '{{.NetworkSettings.Networks.eidolon-targets.IPAddress}}' juice-shop`

## 0 — orchestrator host

```bash
eidolon orchestrator init       # writes ~/.eidolon/orchestrator-token (mode 0600)
eidolon orchestrator start      # http://127.0.0.1:8000
```

In a second terminal:

```bash
eidolon login --host http://127.0.0.1:8000/v1 \
              --token "$(cat ~/.eidolon/orchestrator-token)"
# → writes ~/.eidolon/laptop.json + installs CC skills
claude mcp add eidolon eidolon-mcp
```

## 1 — open the engagement

```bash
eidolon engage start \
  --slug js-dogfood \
  --purpose pentest
# → ENG-<unix>-<hex>, scope_token, jti
```

Capture the `engagement_id`. The initial scope token is overly
permissive by design (full local CIDR, all `recon.*`); we narrow it
next.

```bash
eidolon engage scope <ENG_ID> \
  --target 172.17.0.0/16 \
  --permit recon.read \
  --permit recon.fingerprint \
  --tier confirm \
  --ttl 4h
# → narrowed scope_token, jti
```

## 2 — provision

```bash
eidolon engage provision <ENG_ID> --template web-app-pentest
# → {"network": {"name": "eng-<id>", "driver": "docker"},
#    "vms": [{"vm_name": "kali", "address": "10.43.0.x", ...}]}
```

What happened:
- Per-engagement Docker bridge `eng-<id>` created on `10.43.0.0/24`.
- Kali VM (container) booted with `EIDOLON_VM_TOKEN` and
  `EIDOLON_ENGAGEMENT_ID` baked into env.
- VM agent registered with the orchestrator on first boot.
- Audit chain has `substrate_network_created` and
  `substrate_vm_provisioned` entries.

Verify:

```bash
eidolon engage vms <ENG_ID>
eidolon audit verify
```

## 3 — drive from Claude Code

In Claude Code with the `eidolon` MCP server attached, paste:

> "Pentest Juice Shop at `<juice-shop-ip>:3000`, engagement
> `<ENG_ID>`, web-app-pentest template. Start with passive recon.
> Fire a `noise_threshold` fork before any noisy scan. Fire a
> `mode_change` fork before transitioning to active probes. Hard
> stop at scope edge."

The `eidolon-fork-watcher` skill subscribes to
`/v1/engagements/<id>/forks/stream` and surfaces opened forks back
into chat. The `eidolon-engagement` skill maps natural-language moves
to the right MCP tool calls.

Expected friction points to capture:
- Where does the AI stall waiting for a fork resolution?
- Are forks fired when they should be (before SQLMap, before parent
  network scan)?
- Do scope-edge denials propagate cleanly into chat?
- Does the workspace get useful structured findings?

## 4 — operator-side notes

While the AI works, edit `notes/YYYY-MM-DD.md` directly:

```bash
eidolon engage workspace-edit <ENG_ID>          # opens $EDITOR
eidolon engage workspace-edit <ENG_ID> \
  --note "Confirmed XSS at /search?q=, DOM sink in ResultPage.js"
```

## 5 — close + verify

```bash
eidolon engage close <ENG_ID>
# → status=closed; scope tokens revoked; VMs preserved for forensics
```

If you want to nuke everything:

```bash
eidolon engage erase <ENG_ID>
# → close + substrate teardown + workspace marked erased
```

Verify the audit chain is intact:

```bash
eidolon audit verify
```

A clean run yields:
- `engagement_start`, `scope_token_issued`, `substrate_network_created`,
  `substrate_vm_provisioned` × n,
- `decision_fork_opened` / `_resolved` for each operator decision,
- `tool_dispatch_accepted` / `_denied` per scope-token-bound action,
- `engagement_close` (and `engagement_erased` + `substrate_vm_destroyed`
  × n + `substrate_network_destroyed` if erased),
- A SHA256 chain that reverifies offline.

## 6 — what to capture

For each pass, log:

| Question | Pass? | Friction |
|----------|-------|----------|
| Workspace materialized correctly | y/n | |
| AI fired noise_threshold before SQLMap | y/n | |
| Operator approved/denied a fork in CC | y/n | |
| Scope-edge denial visible in chat | y/n | |
| Findings landed in `findings/<slug>.md` | y/n | |
| `audit verify` clean post-close | y/n | |
| `engage erase` left no orphan resources | y/n | |

File issues for every "no" or any friction. The dogfood pass is the
v0.1 release gate, not a demo.

## Known gaps (v0.1)

- `secrets_inject` happens manually; the substrate's `secrets_inject`
  is wired into the substrate but not yet auto-called on provision.
  Run `docker cp` of secrets manually if the AI needs them in the VM.
- VM agent socket exposure inside the container assumes the operator
  has built a Kali image with `eidolon-agent` baked in; the bundled
  templates use upstream `kalilinux/kali-rolling` so the agent is not
  pre-installed for v0.1. Workaround: `apt install` the agent in
  `bootstrap.sh` or run the AI directly from the host.
- `engage close` does NOT cascade teardown by design — it preserves
  VMs for post-mortem. Use `engage erase` to nuke.
