# Runbook: add a new VM role

Status: Draft, v0.1 target
Last updated: 2026-04-20

Use this when you want to add a new role specialized VM to Eidolon. Examples: a mobile pentest VM, a cloud pentest VM, a custom in house tool VM.

## Decide: is this a Eidolon upstream change or a fork overlay?

Upstream. Generally useful to most operators (mobile pentest, cloud pentest). Ship a PR.

Fork overlay. Firm specific (branded intake VM, proprietary CTI feed server). Ship it in Voyageur or your own fork.

The Eidolon base should stay thin. Default to fork overlay first. Upstream if the pattern is generic.

## 1. Scaffold the VM directory

```
mkdir -p vms/<role>
cd vms/<role>
```

Minimum files:

- `README.md`. One paragraph, what this VM does.
- `provision.sh`. Idempotent Proxmox VM provisioner.
- `cloud-init.yaml`. Base user data. Sets hostname, SSH key, initial package list.
- `job-server/`. FastAPI job server. One endpoint per tool. See existing VMs for the shape.
- `tools/`. One Python module per tool.
- `agent.md`. Subagent definition, if this VM has a scoped agent.

## 2. Define tools

Each tool is a function in `tools/<tool>.py`. Shape:

```python
from eidolon.scope import require_scope
from eidolon.logging import audit_log

@require_scope(session_required=True, allowed_tiers=["autonomous"])
def run_my_tool(job_spec, scope_token):
    audit_log(actor="my-tool-agent", action="run_my_tool", args=job_spec)
    # actually run the tool
    # write outputs to the session workspace only
    return {"job_id": ..., "status": "running"}
```

`require_scope` is the decorator that validates the scope token HMAC, checks the session is open, and checks the command tier.

## 3. Register the tool with the job server

Add to `job-server/routes.py`:

```python
from tools.my_tool import run_my_tool

@app.post("/v1/my-tool")
async def my_tool_endpoint(req: MyToolRequest, scope_token: str = Header(...)):
    return run_my_tool(req.dict(), scope_token)
```

## 4. Define the subagent (if applicable)

`agent.md`:

```markdown
---
name: my-tool-agent
description: One line, what this agent does, which tools it has.
tools: [run_my_tool]
scope_requires: <role>
---

# My Tool Agent

Instructions for the model...

## Rules
- ...
```

## 5. Update the orchestrator

`orchestrator/lib/vm_registry.yaml` gets a new entry:

```yaml
<role>:
  template: <role>-v0.1.qcow2
  vnets: [mgmt, target]
  default_specs:
    vcpu: 2
    ram: 4096
    disk: 60
  gpu_passthrough: false
  job_server_url: http://<role>.eidolon.local:8080
  tools:
    - run_my_tool
```

## 6. Test

Local dev:

```
cd vms/<role>
./provision.sh --dev
# then run the job server
uvicorn job-server.main:app --host 0.0.0.0 --port 8080
```

End to end:

```
eidolon session start --scope ./test-scope.json
eidolon run <role> my-tool --arg1 value1
```

Expect: scope validated, job submitted, result streamed back.

## 7. Document

Add the VM to:

- `docs/architecture/vm-roles.md` (upstream changes)
- `README.md` VM list (upstream changes)
- `CHANGELOG.md` entry

If it is a fork overlay, keep documentation in the fork's own docs directory.

## 8. Ship

Upstream PR or fork commit. GPG sign. Security sensitive VM (anything touching scope tokens, session lifecycle, or auth) needs multi maintainer review.

## Common mistakes

Writing tool outputs somewhere other than the active session workspace. All tool outputs must go to `/mnt/session/<session_id>/` inside the VM.

Skipping `require_scope`. Silent scope bypass. Grep for it in code review.

Not adding an audit_log call. Violates the auditability NFR. Every tool action must log.

Forgetting the command tier. Defaults to prohibited. Set it explicitly.

## See also

- `../architecture/vm-roles.md`
- `../architecture/agent-orchestration.md`
