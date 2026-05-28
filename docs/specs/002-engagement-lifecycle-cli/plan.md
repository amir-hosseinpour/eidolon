# Plan: Engagement lifecycle CLI

Spec: `./spec.md`
Status: Approved
Updated: 2026-04-26

## Approach

Replace the existing `eidolon session` Click group with `eidolon engagement`. Add `erase` and `list` orchestrator endpoints. Add a small Ed25519 key-management module that generates the audit signing keypair on first use. The Cert of Destruction is a Pydantic model serialized to JSON; head-hash fields are placeholders for Spec 004 to fill in. CLI exit codes: 0 success, 1 orchestrator error, 2 client/CLI usage error.

## Architecture

- Touched: `eidolon/cli/main.py`, `eidolon/orchestrator/app/routers/engagements.py`, `eidolon/orchestrator/lib/engagements.py`.
- Added: `eidolon/orchestrator/lib/keys.py` (Ed25519 key bootstrap), `eidolon/orchestrator/lib/cert_of_destruction.py` (model + signer), `eidolon/cli/engagement.py` (engagement subcommands), `tests/test_engagement_cli.py`, `tests/test_cert_of_destruction.py`.

## Data model

```python
class CertificateOfDestruction(BaseModel):
    engagement_id: str
    opened_at: int
    closed_at: int
    erased_at: int
    audit_head_at_open: str   # hex sha256, "0" * 64 in v0.1 stub
    audit_head_at_close: str  # ditto
    public_key: str           # base64 Ed25519 pub key
    signature: str            # base64 Ed25519 signature over canonical JSON of the above fields
```

Sign-over-canonical-json: `signature = ed25519_sign(canonical_json({fields_minus_signature, fields_minus_public_key}))`. Verification reproduces the canonical JSON and checks signature against `public_key`.

## Contracts

### API endpoints

`POST /v1/engagements/{engagement_id}/erase` — closes if open, emits destruction audit event, returns `CertificateOfDestruction`. Idempotent: re-erase returns the existing cert.

`GET /v1/engagements` — returns `{engagements: [Engagement, ...]}`.

`GET /v1/engagements/{id}/issued-tokens` — returns `{jtis: [...]}` (just the JTIs).

`GET /v1/engagements/{id}/audit-head` — returns `{head: "..."}` (stub `"0" * 64` until Spec 004).

### CLI surface

`eidolon engagement open --slug S --purpose P [--rules-of-engagement FILE]`
`eidolon engagement scope <id> --target T (multi) --permit P (multi) --tier T --ttl D`
`eidolon engagement show <id> [--with-tokens] [--with-audit-head]`
`eidolon engagement close <id>`
`eidolon engagement erase <id>`
`eidolon engagement list`

`--ttl` parser: `\d+(s|m|h)` → seconds. `8h` = 28800. Reject unrecognized.

### Events / log lines

`engagement_erased`: emitted to audit hook with `{engagement_id, erased_at, cert_hash}`.

## Migrations

None. v0.2 migrates the in-memory store to SQLite.

## Security review

- Threats: forged cert, swapped public key. Mitigation: sign the public key into the cert (the cert IS the public key + signature over the rest); a verifier needs an out-of-band trust anchor for the public key (operator's ROE). v0.1 documents this.
- Private key file at `~/.eidolon/keys/audit.ed25519`, mode 0600. Bootstrap creates the dir 0700.
- Audit emit: yes, `engagement_erased` event.

## Test strategy

- `tests/test_cert_of_destruction.py`: generate keypair, sign a cert, verify, tamper with one byte, verify fails.
- `tests/test_engagement_cli.py`: use Click's `CliRunner` to invoke the CLI against a mocked orchestrator (httpx mock or a TestClient adapter). Cover AC-1..AC-7.
- `tests/test_engagement_erase.py`: API-level test that erase on open engagement closes + emits cert; idempotent re-erase returns same cert.

## Risks and mitigations

1. **Click boilerplate for nested groups.** Mitigation: standard pattern.
2. **`~/.eidolon/keys/` writable in CI.** Mitigation: `EIDOLON_HOME` env var; tests set to a tmp dir.
3. **httpx-vs-CliRunner integration.** Mitigation: use Click's `CliRunner` and `httpx.MockTransport` or just spin the FastAPI TestClient and route the CLI through it. Pick the simplest that works.

## Alternatives considered

- **Skip erase + cert in v0.1, defer to v0.2.** Rejected. The Cert of Destruction is *the* differentiator per ADR-0008. Shipping erase without it would dilute the v0.1 story.
- **PDF cert via ReportLab.** Rejected for v0.1; cosmetic, not load-bearing. Stub omitted; signed JSON is the artifact.
- **Per-engagement signing key.** Rejected; rotation complexity not worth v0.1 friction. One operator key per orchestrator install.

## Out of scope (technical)

- SQLite persistence (v0.2).
- LUKS or actual volume erase (Voyageur).
- Cert verification CLI (Spec 004 ships `eidolon cert verify` because it needs the audit chain).
