# Scope

Overwritten by the orchestrator on engagement open with declared scope
(domains, hostnames, IP ranges, time windows, exclusions). Do not edit
by hand.

Anything outside the declared scope must go through a `scope_edge`
decision fork before the orchestrator dispatches a tool call.
