# Plan: [Feature Name]

Spec: `../spec.md`
Status: Draft | Approved
Updated: YYYY-MM-DD

## Approach

One paragraph. The technical solution direction. Not the implementation details — those go in tasks.md.

## Architecture

What components change? What's added? What's removed?

- Touched: `orchestrator/app/routers/X.py`, `orchestrator/lib/Y.py`
- Added: `orchestrator/lib/Z.py`
- Diagrams: `docs/diagrams/...`

## Data model

If the feature changes any data shape, document it here. Pydantic models, table schemas, JWT payloads, file formats.

## Contracts

External and internal interfaces.

### API endpoints (if any)

`POST /engagements/{id}/X` — request: `{...}`, response: `{...}`, errors: `403 if scope mismatch`.

### CLI surface (if any)

`eidolon foo bar [--flag]` — what it does, what it prints.

### Events / log lines (if any)

Structured log event names, fields, when emitted.

## Migrations

DB migrations, file moves, config changes that need to happen on upgrade. Empty if none.

## Security review

- Threats considered: …
- Scope token enforcement: yes/no, where
- Command tier: autonomous / confirm / prohibited
- Audit log entries emitted: …

## Test strategy

What tests prove the spec's acceptance criteria? Which are unit, which integration, which e2e? Where do they live?

## Risks and mitigations

Top 3 risks of this approach. What goes wrong? How do we know early?

## Alternatives considered

What else we considered, why we didn't pick it. One paragraph each. Keeps the decision auditable.

## Out of scope (technical)

Distinct from spec out-of-scope — this is what the technical approach does NOT do, even if the spec implies it.
