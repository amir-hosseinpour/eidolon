---
name: eidolon-engagement
description: Natural-language wrapper to drive an Eidolon engagement end-to-end. Use when the operator wants to start, scope, observe, or close an engagement using plain English instead of CLI flags or MCP tool calls directly.
---

# Eidolon — engagement orchestration

Translates operator-friendly phrasing into Eidolon MCP tool calls. Pairs
`eidolon-core` (which defines the safety rails) and `eidolon-fork-watcher`
(which surfaces operator decisions).

## Common moves

### "Start a web-app pentest against scope X"

1. Confirm the slug, RoE, and CIDRs with the operator.
2. Call `template_info` for `web-app-pentest` and read out the required
   secrets. If any are missing, prompt the operator to run
   `eidolon secrets put <label>` (do not request raw secret values in chat).
3. Call `engage_start` with `purpose=pentest`, the operator's slug, and the
   scope document. Quote the returned `engagement_id` and `scope_token`
   prominently — the scope token is shown only once.
4. Offer to start `eidolon-fork-watcher` on this engagement.

### "Scope this engagement to <CIDR> for the next 4 hours"

Call `scope_token_issue` with `targets=[<cidr>]`, `permits=<asked>`,
`tier=confirm`, `ttl_seconds=14400`. Echo the new `jti` (not the token).

### "Approve / deny the open fork"

Look up open forks via `fork_list`, identify the one the operator means,
call `fork_resolve` with their resolution and rationale. Echo the resolved
fork id and resolution back.

### "Wrap up engagement <id>"

1. List open forks; refuse to close while any are open unless the operator
   explicitly overrides.
2. Call `engage_close`. Workspace stays on disk.
3. Offer `engage_erase` only if the operator asks for full destruction.

## Style

- Keep responses short. The operator is mid-engagement; verbose summaries
  waste their attention.
- Echo identifiers back as code spans (e.g. `ENG-...`, `JTI-...`) so they
  are easy to copy.
- Never echo bearer tokens, scope tokens (after first issue), or secret
  values back to chat.
