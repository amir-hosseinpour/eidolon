---
name: eidolon-core
description: Root behavior for operating Eidolon engagements through Claude Code. Loads laptop config, knows MCP tool surface, defines safety rails. Auto-load when the user references engagements, scope tokens, decision forks, or templates.
---

# Eidolon — core operating skill

You are operating an Eidolon orchestrator on the user's behalf. Eidolon is the
runtime for offensive-security engagements: it provisions VMs from templates,
issues scope tokens, runs decision forks for high-risk choices, and writes
every action to a hash-chained audit log.

## Connection

Configuration lives at `~/.eidolon/laptop.json`:

```json
{ "host": "http://orchestrator:8000/v1", "token": "<bearer>" }
```

If that file is missing, run `eidolon login --host <url> --token <bearer>` first.

The `eidolon-mcp` MCP server (registered with Claude Code via
`claude mcp add eidolon eidolon-mcp`) exposes the orchestrator REST surface
as MCP tools. Prefer those over shelling out to the `eidolon` CLI for state
mutation. Use the CLI for one-shot inspection (e.g. `eidolon health`).

## MCP tool index

| Resource | Tools |
|---|---|
| Engagements | `engage_start`, `engage_list`, `engage_get`, `engage_close`, `engage_erase` |
| Scope tokens | `scope_token_issue`, `scope_token_revoke` |
| Decision forks | `fork_open`, `fork_list`, `fork_resolve` |
| Secrets broker | `secret_put`, `secret_present`, `secret_delete` (never echo values back) |
| Templates | `template_list`, `template_info` |
| Workspace | `workspace_write_note`, `workspace_write_decision`, `workspace_write_finding`, `workspace_read_log` |

## Safety rails

- Never call `engage_erase` without explicit operator confirmation. It is irreversible.
- Never echo a secret value into chat. `secret_present` returns boolean only;
  use the in-VM agent socket for actual fetch.
- Before any tool dispatch outside an autonomous-tier scope, open a decision
  fork (`fork_open`) and wait for the operator. Three strategic types you fire:
  `path_selection`, `mode_change`, `noise_threshold`. Two safety types fire
  automatically from the orchestrator: `scope_edge`, `cred_disposition`.
- Workspace writes are operator-visible Markdown. Treat them as the engagement's
  notebook. Append-only via `workspace_write_note`, structured records via
  `workspace_write_decision` and `workspace_write_finding`.

## When unsure

Ask the operator. The orchestrator's audit log captures every fork and
resolution; "I asked first" is always cheaper than "I shouldn't have."
