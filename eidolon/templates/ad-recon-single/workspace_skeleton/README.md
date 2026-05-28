# Engagement Workspace - ad-recon-single

This directory becomes `$EIDOLON_HOME/engagements/<id>/workspace/` on
engagement open. Evidence is hash-anchored into the audit log via the
orchestrator.

Layout:

- `notes/`     - daily working notes (`YYYY-MM-DD.md`).
- `findings/`  - one Markdown file per confirmed finding.
- `decisions/` - one Markdown file per resolved decision fork.
- `proofs/`    - command transcripts, tool output, screenshots.
- `loot/`      - hashes, tickets, certs (encrypted at rest where possible).
- `scope.md`   - declared scope (do not edit by hand).
- `domain.md`  - per-domain notes, trust map, DC list.
