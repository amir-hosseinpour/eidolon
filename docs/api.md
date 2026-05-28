# Eidolon — API reference

The orchestrator exposes one HTTP API. Every other surface (operator
CLI, MCP server, in-VM agent socket) is a thin client over it.

There are three auth contexts:

| Context | Header | Issued by |
|---------|--------|-----------|
| Operator (CLI, MCP) | `Authorization: Bearer <orch-token>` | `eidolon orchestrator init` |
| Tool dispatch | `X-Scope-Token: <jwt>` | `engage start` / `engage scope` |
| VM agent | `Authorization: Bearer <vm-token>` | substrate at provision time |

`require_bearer` gates `/v1/engagements/**` and `/v1/tools/**`. The VM
agent routes use their own per-VM token — do not send the operator
bearer there.

## REST surface

All paths are under `/v1`. JSON in/out unless otherwise noted.

### Health

```
GET  /v1/health
     → 200 {"status": "ok", "service": "eidolon-orchestrator"}
```

No auth.

### Engagements

```
POST /v1/engagements/start
     body: {slug, purpose, scope: {allowed_cidrs, allowed_actions,
                                   tier, rules_of_engagement,
                                   expires_at?}}
     → 201 {engagement_id, scope_token, jti, expires_at, status}

GET  /v1/engagements
     → 200 {engagements: [...]}

GET  /v1/engagements/{engagement_id}
     → 200 {engagement: {...}}

GET  /v1/engagements/{engagement_id}/issued-tokens
     → 200 {jtis: [...]}

GET  /v1/engagements/{engagement_id}/audit-head
     → 200 {head: "<sha256>"}

POST /v1/engagements/{engagement_id}/close
     → 200 {engagement: {..., status: "closed"}}

POST /v1/engagements/{engagement_id}/erase
     → 200 {engagement: {..., status: "erased",
                          audit_head_at_close}}
```

`purpose` ∈ `{pentest, research, ctf, training}`. `tier` ∈
`{autonomous, confirm, prohibited}`. Engagement ids are
`ENG-<14 hex>`.

### Provisioning

```
POST /v1/engagements/{engagement_id}/provision
     body: {template}
     → 201 {engagement_id, template, network: {...},
            vms: [{handle_id, vm_name, driver, network,
                   address, status, ...}]}

POST /v1/engagements/{engagement_id}/teardown
     → 200 {engagement_id, vms_destroyed, network_destroyed}

GET  /v1/engagements/{engagement_id}/vms
     → 200 {engagement_id, vms: [...]}
```

Provision picks the first available substrate from the template's
`substrate_support` list. Each VM gets a fresh `vm_token` injected as
`EIDOLON_VM_TOKEN` env. `engage erase` runs teardown automatically;
`engage close` does NOT — it preserves VMs for forensics.

### Scope tokens

```
POST /v1/engagements/{engagement_id}/scope-token
     body: {targets, permits, tier, ttl_seconds?,
            rules_of_engagement?}
     → 201 {token, jti, engagement_id, expires_at}

POST /v1/engagements/{engagement_id}/scope-token/revoke
     body: {jti}
     → 204
```

`ttl_seconds` capped at 24 h. Tokens are HS256 JWTs signed with the
orchestrator key. `revoke` flags the `jti` in the revocation store; the
verifier rejects revoked or expired tokens immediately.

### Decision forks

```
POST /v1/engagements/{engagement_id}/forks
     body: {fork_type, prompt, context}
     → 201 {fork: {id, status: "open", ...}}

POST /v1/engagements/forks/{fork_id}/resolve
     body: {resolution, operator, rationale?}
     → 200 {fork: {status: "approved"|"denied", ...}}

GET  /v1/engagements/{engagement_id}/forks?status=open
     → 200 {forks: [...]}

GET  /v1/engagements/{engagement_id}/forks/stream
     → 200 text/event-stream
       event: opened|resolved
       data:  {event, fork: {...}}
       :heartbeat every 15s
```

`fork_type` ∈ `{path_selection, mode_change, cred_disposition,
noise_threshold, scope_edge}`. See [`decision-forks.md`](decision-forks.md).

### Tool dispatch

```
POST /v1/tools/dispatch
     headers: X-Scope-Token: <jwt>
     body: {engagement_id, tool_id, target?, action, args?,
            confirm_token?}
     → 200 {accepted: true,  tier, dispatch_id}
       403 {detail: {reason: "tier_prohibited"}}
       428 {detail: {reason: "confirm_token_required"}}
       4xx {detail: {reason: <ScopeError reason>}}
```

`tool_id` resolves to a tier (autonomous / confirm / prohibited).
`confirm_token` is required for confirm-tier dispatches. Every
accepted/denied dispatch is recorded in the dispatch store and emitted
on the audit chain.

### VM agent (per-VM token)

```
POST /v1/vm-agent/register
     headers: Authorization: Bearer <vm-token>
     body: {vm_name}
     → 200 {agent: {...}}

POST /v1/vm-agent/heartbeat
     headers: Authorization: Bearer <vm-token>
     → 200 {agent: {...}}

POST /v1/vm-agent/secrets
     headers: Authorization: Bearer <vm-token>
     body: {label}
     → 200 {label, value}
       404 {detail: "secret_not_found"}
```

These routes are gated by the per-VM token, not the operator bearer.
Reuse a revoked or unknown VM token returns `401 vm_token_invalid`.

## MCP tools (19 total)

`eidolon-mcp` is a stdio MCP server bridging Claude Code (or any MCP
client) to the orchestrator REST API. Connect from Claude Code:

```bash
claude mcp add eidolon eidolon-mcp
```

Tool list (output of `tools/list`):

### Engagements (7)

| Tool | Purpose |
|------|---------|
| `engage_start` | Start a new engagement; mints initial scope token. |
| `engage_list` | List engagements visible to the orchestrator. |
| `engage_get` | Fetch a single engagement by id. |
| `engage_close` | Close an engagement. Revokes scope tokens. |
| `engage_erase` | Erase an engagement; close-then-erase if active. |
| `scope_token_issue` | Issue an additional scope token under an engagement. |
| `scope_token_revoke` | Revoke a scope token by `jti`. |

### Decision forks (3)

| Tool | Purpose |
|------|---------|
| `fork_open` | Open a structured pause for operator decision. |
| `fork_list` | List forks for an engagement, optionally by status. |
| `fork_resolve` | Resolve a fork as approved or denied. |

### Secrets (3)

| Tool | Purpose |
|------|---------|
| `secret_put` | Store a secret in the broker (env / Keychain / 1Password). |
| `secret_delete` | Delete a secret by label. |
| `secret_present` | Boolean — does this label resolve? Never returns value. |

`secret_get` does not exist. Values stay out of Claude Code chat by
design. In-VM tools fetch them via the `eidolon-agent` socket.

### Templates (2)

| Tool | Purpose |
|------|---------|
| `template_list` | List available templates (operator + bundled). |
| `template_info` | Get the validated template document by name. |

### Workspace (4)

| Tool | Purpose |
|------|---------|
| `workspace_write_note` | Append to `notes/YYYY-MM-DD.md`. |
| `workspace_write_decision` | Write `decisions/<fork>.md` after a fork resolution. |
| `workspace_write_finding` | Write `findings/<slug>.md`. |
| `workspace_read_log` | Read `log.jsonl` events. |

## Errors

REST errors return JSON of the form `{"detail": "<reason>"}` (or
`{"detail": {"reason": "..."}}` for tool dispatch). Common reasons:

| HTTP | Reason | When |
|------|--------|------|
| 401  | `missing_bearer` / `vm_token_invalid` | Auth missing or bad |
| 403  | `tier_prohibited`     | Dispatch into a prohibited tier |
| 404  | `engagement_not_found` / `tool_unknown` / `fork_not_found` / `secret_not_found` | Lookup miss |
| 409  | `engagement_<status>` / `fork_not_open` | State transition refused |
| 410  | `token_revoked`       | jti revoked |
| 428  | `confirm_token_required` | Confirm-tier dispatch w/o confirm token |

MCP tools surface REST errors as `RestError(status, detail)` and return
a non-OK MCP `CallToolResult` whose text payload includes the status
and the underlying detail.

## CLI

`eidolon` covers the same surface from the shell. See
[`README.md`](../README.md) Quick start for the canonical commands.

```
eidolon orchestrator init|start
eidolon login --host <url> --token <token>
eidolon engage start|list|show|close|erase|scope|workspace-edit
eidolon engage provision|teardown|vms
eidolon fork list|show|open|resolve
eidolon secrets backend|list|store|get|revoke
eidolon templates list|info
eidolon audit verify
eidolon skills install
```
