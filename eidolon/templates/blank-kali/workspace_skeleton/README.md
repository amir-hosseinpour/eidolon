# Engagement Workspace

This directory is the on-disk root for a single engagement opened from the
`blank-kali` template. It will be copied to
`$EIDOLON_HOME/engagements/<id>/workspace/` when the engagement is opened.

Conventions (filled in by the orchestrator and the operator over time):

- `notes/`  - free-form daily notes (`YYYY-MM-DD.md`).
- `findings/` - one Markdown file per confirmed finding.
- `decisions/` - one Markdown file per resolved decision fork.
- `scope.md` - copy of the declared scope at engagement open.
- `targets.md` - hosts, IPs, URLs in scope, with notes.

Everything in this workspace is treated as engagement evidence: it is
hash-anchored into the audit log when written through the orchestrator,
and erased atomically on `eidolon engage close --erase`.
