---
name: eidolon-fork-watcher
description: Subscribe to the Eidolon fork SSE stream and surface new decision forks to the operator. Use when the operator says "watch forks", "subscribe to forks", or starts an engagement and wants the watcher running.
---

# Eidolon — fork watcher

A decision fork is a structured pause: the orchestrator (or AI) opens one when
a high-risk action needs operator approval. New forks push out as Server-Sent
Events on `GET /v1/engagements/{engagement_id}/forks/stream`.

## When to engage

Operator triggers explicitly: "watch forks for engagement X", "subscribe", or
right after `engage_start`.

## How

1. Read `~/.eidolon/laptop.json` for `host` + `token`.
2. Open an SSE connection to
   `{host}/engagements/{engagement_id}/forks/stream` with
   `Authorization: Bearer {token}` and `Accept: text/event-stream`.
3. The stream replays open forks first, then sends `:heartbeat` lines every
   ~15s, then real events (`event: opened`, `event: resolved`).
4. For each `event: opened`, surface the fork to the operator with:
   - fork id
   - fork type (one of `scope_edge`, `cred_disposition`, `path_selection`,
     `mode_change`, `noise_threshold`)
   - prompt
   - context dict
5. When the operator answers, call the `fork_resolve` MCP tool with their
   choice (`approved`/`denied`), their name, and their rationale.

## Stop

When the operator says "stop watching" or the engagement closes. Closing the
SSE connection is fine — the orchestrator does not require a specific bye.

## Failure modes

- Network drop: reconnect with exponential backoff (2s, 4s, 8s, max 30s).
  Replay buffer means re-subscribe is cheap.
- 401: token rotated. Tell the operator to `eidolon login` again.
- 404: engagement not found or already erased. Stop, surface the error.
