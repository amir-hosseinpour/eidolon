# Eidolon — decision forks

A decision fork is a structured pause where the orchestrator (or the AI)
hands the wheel to the operator. Forks exist for two reasons:

1. **Hard safety** — the orchestrator refuses to dispatch an action and
   raises a fork. The AI cannot suppress these.
2. **Strategic judgment** — the AI suspects a choice is operator-grade
   (legality, noise, persistence, scope ambiguity) and asks rather than
   guesses.

Five fork types cover both. Templates declare which apply per
engagement.

## Lifecycle

```
                    ┌──────────────┐
   AI / orchestrator│  fork_open   │
                    └──────┬───────┘
                           │ POST /v1/engagements/{eng}/forks
                           ▼
                    ┌──────────────┐
                    │  status=open │  ← persisted in SQLite
                    └──────┬───────┘
                           │ broadcast on SSE
                           ▼
        ┌──────────────────────────────────┐
        │ Operator's Claude Code subscriber│  GET .../forks/stream
        └──────────────┬───────────────────┘
                       │ chat message → fork_resolve
                       ▼
                ┌──────────────────────┐
                │ status=approved|denied│
                └──────────┬────────────┘
                           │
                ┌──────────┴───────────┐
                ▼                      ▼
    decisions/<fork-id>.md      audit chain entry
    in engagement workspace     decision_fork_resolved
```

A fork has an `id` of the form `FORK-<unix>-<6 hex>`. It carries:

- `engagement_id`, `fork_type`, `prompt`, `context` (free-form JSON),
- `created_at`, `resolved_at`, `resolved_by`, `resolution`,
  `rationale`,
- `status` ∈ `{open, approved, denied, expired}`.

`expired` is reserved for v0.2 — the v0.1 store does not auto-expire.

## The five types

### `scope_edge`  *(orchestrator-fired, hard safety)*

The orchestrator is about to dispatch a tool whose target/action would
exceed the verified scope token. The dispatch is held; a fork is
opened. Approval mints a one-shot extension; denial drops the action.

Fires on: target outside CIDR allowlist; action not in `permit` list;
tier escalation request from `confirm` to `autonomous`.

Example prompt:
> "nmap targeting 10.0.5.7 is outside scope (10.0.0.0/24). Approve
> one-shot scan or expand engagement scope?"

### `cred_disposition`  *(operator-grade, hard safety)*

The AI has discovered or recovered credentials, hashes, tickets, or
sessions, and intends to do something with them beyond writing them
into the workspace `findings/`. Forks fire before relay, replay,
external upload, or storage outside the engagement.

Fires on: pass-the-hash chain, kerberoast offload, NTLM relay, posting
secrets to a paste service, copying secrets to the operator's home
directory.

Example prompt:
> "Found 3 NTLM hashes for `CORP\sql_svc`. Approve crackstation submit,
> local hashcat (GPU VM), or hold in workspace only?"

### `mode_change`  *(operator-grade)*

The AI wants to transition from a passive/observational mode into an
active/intrusive one. Examples: passive recon → active exploitation,
read-only LDAP → AS-REP roast, browse-only → form fuzzing,
authenticated browse → privilege escalation attempt.

This fork captures the operator's "are we ready to be loud" decision
and pins it to the audit chain.

### `noise_threshold`  *(operator-grade)*

The AI is about to issue a request that materially raises detection
risk: full-port nmap, large ffuf wordlists, sqlmap with `--risk=3
--level=5`, mass SPN sweep, a wide nuclei profile.

Forks fire when an estimated request count or bandwidth crosses a
template-defined threshold, or when the AI judges the action would
trip standard SIEM rules.

### `path_selection`  *(operator-grade)*

Two or more roughly-equivalent attack paths are open and the AI wants
the operator to pick. Common case: "we can pivot via ADCS ESC1, via
Kerberos delegation, or via SCCM — which line do you want me on?"

Forks of this type carry the alternatives in `context.options`.

## Who fires what

| Type               | Origin                | Why operator-only resolution |
|--------------------|-----------------------|------------------------------|
| `scope_edge`       | orchestrator (hard)   | Authority outside the AI |
| `cred_disposition` | orchestrator + AI     | Legal + handling consequences |
| `mode_change`      | AI                    | Engagement strategy + ROE |
| `noise_threshold`  | AI                    | Tradeoff vs blue-team detection |
| `path_selection`   | AI                    | Operator preference + time budget |

The AI MUST NOT resolve a fork it opened. Resolution requires the
operator's `eidolon fork resolve` (or the MCP `fork_resolve` tool from
the operator's Claude Code).

## Template policy

Templates declare default fork policies under `decision_forks:`. Each
entry is `{type, auto_resolve, default_message}`:

```yaml
decision_forks:
  - type: scope_edge
    auto_resolve: false
    default_message: >
      Operator review required before testing hosts not in declared scope.
```

`auto_resolve: true` is reserved for v0.2 (e.g., auto-approve a
`noise_threshold` fork during a `training` engagement). v0.1 always
requires a human resolver.

`default_message` is rendered when the AI fires the fork without an
explicit prompt.

## REST surface

```
POST /v1/engagements/{engagement_id}/forks
  body: {fork_type, prompt, context}
  201:  {fork: {id, status: "open", ...}}

POST /v1/engagements/forks/{fork_id}/resolve
  body: {resolution: "approved"|"denied", operator, rationale}
  200:  {fork: {status: "approved", resolved_by, ...}}

GET  /v1/engagements/{engagement_id}/forks?status=open
  200:  {forks: [...]}

GET  /v1/engagements/{engagement_id}/forks/stream
  200:  text/event-stream
        event: opened|resolved
        data:  {event, fork: {...}}
        :heartbeat every 15s
```

The SSE stream replays current open forks on connect, then emits live
events for the engagement until the client drops.

## CLI

```bash
eidolon fork list <ENG_ID> [--status open]
eidolon fork show <ENG_ID> <FORK_ID>
eidolon fork open <ENG_ID> --type scope_edge --prompt "..." --context '{...}'
eidolon fork resolve <FORK_ID> --resolution approved --operator damion --rationale "..."
```

## MCP tools

`fork_open`, `fork_list`, `fork_resolve`. Same semantics as the REST
endpoints; the operator's Claude Code surfaces them as conversational
moves.

## Persistence

Resolved forks are written to two places:

1. The audit chain: `decision_fork_opened` and `decision_fork_resolved`
   entries with the fork id, type, resolver, and resolution.
2. The engagement workspace: `decisions/<fork-id>.md` (markdown summary
   of the prompt, context, resolution, rationale, and operator).

The chain is the source of truth; `decisions/` is operator-readable.

Lib: `eidolon.orchestrator.lib.forks`.
Routes: `eidolon.orchestrator.app.routers.forks`.
