# Scope

This file is overwritten by the orchestrator on engagement open with the
declared scope (hosts, IPs, URLs, time windows, exclusions). Do not edit
by hand: edits will be lost the next time the engagement is reopened.

Anything outside the declared scope must go through a `scope_edge`
decision fork before the orchestrator will dispatch a tool call against it.
