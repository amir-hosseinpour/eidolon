# Tasks: Engagement lifecycle CLI

Spec: `./spec.md`
Plan: `./plan.md`
Status: In Progress

## Tasks

### T-01 [P] Failing tests for cert generate + sign + verify + tamper

File: `tests/test_cert_of_destruction.py`

`test_sign_and_verify_roundtrips`, `test_tampered_field_fails_verify`, `test_swapped_public_key_fails_verify`. Must fail before T-04.

### T-02 [P] Failing tests for erase endpoint idempotency

File: `tests/test_engagement_erase.py`

`test_erase_open_engagement_closes_and_returns_cert`, `test_erase_returns_same_cert_on_replay`, `test_erase_unknown_engagement_returns_404`.

### T-03 [P] Failing tests for engagement CLI

File: `tests/test_engagement_cli.py`

`test_engagement_open_prints_id`, `test_engagement_scope_mints_token`, `test_engagement_close_then_scope_returns_error`, `test_engagement_erase_writes_cert_file`, `test_engagement_show_returns_state`, `test_engagement_list_prints_table`. Use Click `CliRunner` + httpx `MockTransport` against the FastAPI TestClient.

### T-04 Implement Ed25519 key bootstrap

File: `eidolon/orchestrator/lib/keys.py`

`get_audit_signing_key()` returns `(SigningKey, VerifyKey)`. On first call, creates `~/.eidolon/keys/audit.ed25519` (mode 0600) and `.pub`. `EIDOLON_HOME` env override.

### T-05 Implement CertificateOfDestruction model + signer

File: `eidolon/orchestrator/lib/cert_of_destruction.py`

Pydantic model. `sign_cert(data)` and `verify_cert(cert)` functions. Canonical JSON serializer. Use cryptography or PyNaCl (PyNaCl is simpler).

### T-06 Add erase + list + tokens + audit-head endpoints

File: `eidolon/orchestrator/app/routers/engagements.py`

Plus EngagementStore tracks issued JTIs per engagement (in memory). Cert cached on engagement record after first erase.

### T-07 Replace session CLI with engagement CLI

File: `eidolon/cli/main.py` (replace `session` group), `eidolon/cli/engagement.py` (new — actual command implementations).

`--ttl` parser. `~/.eidolon/certs/` directory bootstrap.

### T-08 Run make verify, fix anything

## Done when

- [ ] All AC-1..AC-7 tests pass
- [ ] `make verify` passes
- [ ] No constitution rule violations introduced (CON-1, CON-9, CON-12)
- [ ] PRD/ROADMAP unchanged (already reflects this scope)
