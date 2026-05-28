from __future__ import annotations

import json as _json
import os
import sys
from datetime import UTC
from pathlib import Path
from typing import Any

import click
import httpx
from rich.console import Console
from rich.table import Table

console = Console()
DEFAULT_BASE = "http://127.0.0.1:8000/v1"


def _laptop_config_path() -> Path:
    return Path.home() / ".eidolon" / "laptop.json"


def _local_token_path() -> Path:
    home = os.environ.get("EIDOLON_HOME")
    base = Path(home) if home else Path.home() / ".eidolon"
    return base / "orchestrator-token"


def resolve_token(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    env = os.environ.get("EIDOLON_TOKEN")
    if env:
        return env
    laptop = _laptop_config_path()
    if laptop.exists():
        try:
            data = _json.loads(laptop.read_text())
            tok = data.get("token")
            if isinstance(tok, str) and tok:
                return tok
        except (OSError, ValueError):
            pass
    local = _local_token_path()
    if local.exists():
        text = local.read_text().strip()
        if text:
            return text
    if os.environ.get("EIDOLON_HOME"):
        from eidolon.orchestrator.lib.auth import load_or_create_token

        return load_or_create_token()
    return None


def get_client(base_url: str) -> httpx.Client:
    """Return the HTTP client. Tests monkeypatch this to inject ASGITransport."""
    return httpx.Client(base_url=base_url, timeout=10.0)


def _request(ctx: click.Context, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    base = ctx.obj.get("base_url", DEFAULT_BASE)
    headers = dict(kwargs.pop("headers", {}))
    token = resolve_token(ctx.obj.get("token"))
    if token and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {token}"
    with get_client(base) as client:
        try:
            resp = client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            console.print(f"[red]request failed:[/red] {exc}")
            sys.exit(2)
    if resp.status_code >= 400:
        console.print(f"[red]{resp.status_code}[/red] {resp.text}")
        sys.exit(1)
    if resp.status_code == 204:
        return {}
    body: dict[str, Any] = resp.json()
    return body


_TTL_SUFFIX_SECONDS = {"s": 1, "m": 60, "h": 3600}


def parse_ttl(value: str) -> int:
    if not value or value[-1] not in _TTL_SUFFIX_SECONDS:
        raise click.BadParameter(f"invalid ttl: {value} (expect <int><s|m|h>)")
    try:
        n = int(value[:-1])
    except ValueError as exc:
        raise click.BadParameter(f"invalid ttl: {value}") from exc
    return n * _TTL_SUFFIX_SECONDS[value[-1]]


@click.group()
@click.option("--base-url", default=DEFAULT_BASE, show_default=True)
@click.option("--token", default=None, help="Bearer token override.")
@click.pass_context
def main(ctx: click.Context, base_url: str, token: str | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["base_url"] = base_url
    ctx.obj["token"] = token


@main.group()
def engage() -> None:
    """Engagement lifecycle commands."""


@engage.command("start")
@click.option("--slug", required=True)
@click.option(
    "--purpose",
    type=click.Choice(["pentest", "research", "ctf", "training"]),
    required=True,
)
@click.option(
    "--rules-of-engagement",
    type=click.Path(exists=True, path_type=Path),
    help="Path to a Rules of Engagement document. Contents stored on the engagement.",
)
@click.pass_context
def engage_start(
    ctx: click.Context,
    slug: str,
    purpose: str,
    rules_of_engagement: Path | None,
) -> None:
    roe_text = rules_of_engagement.read_text() if rules_of_engagement else ""
    scope = {
        "allowed_cidrs": [],
        "allowed_actions": [],
        "tier": "autonomous",
        "rules_of_engagement": roe_text,
    }
    data = _request(
        ctx,
        "POST",
        "/engagements/start",
        json={"slug": slug, "purpose": purpose, "scope": scope},
    )
    console.print_json(data=data)


@engage.command("scope")
@click.argument("engagement_id")
@click.option("--target", multiple=True, required=True, help="CIDR (repeatable)")
@click.option("--permit", multiple=True, required=True, help="ScopeAction (repeatable)")
@click.option(
    "--tier",
    type=click.Choice(["autonomous", "confirm", "prohibited"]),
    required=True,
)
@click.option("--ttl", default="8h", show_default=True, help="<int>s|m|h")
@click.option("--rules-of-engagement", default="", help="Free text, optional.")
@click.pass_context
def engage_scope(
    ctx: click.Context,
    engagement_id: str,
    target: tuple[str, ...],
    permit: tuple[str, ...],
    tier: str,
    ttl: str,
    rules_of_engagement: str,
) -> None:
    payload = {
        "targets": list(target),
        "permits": list(permit),
        "tier": tier,
        "ttl_seconds": parse_ttl(ttl),
        "rules_of_engagement": rules_of_engagement,
    }
    data = _request(ctx, "POST", f"/engagements/{engagement_id}/scope-token", json=payload)
    console.print_json(data=data)


@engage.command("show")
@click.argument("engagement_id")
@click.option("--with-tokens", is_flag=True)
@click.option("--with-audit-head", is_flag=True)
@click.pass_context
def engage_show(
    ctx: click.Context,
    engagement_id: str,
    with_tokens: bool,
    with_audit_head: bool,
) -> None:
    data = _request(ctx, "GET", f"/engagements/{engagement_id}")
    if with_tokens:
        data["issued_tokens"] = _request(
            ctx, "GET", f"/engagements/{engagement_id}/issued-tokens"
        )
    if with_audit_head:
        data["audit_head"] = _request(ctx, "GET", f"/engagements/{engagement_id}/audit-head")
    console.print_json(data=data)


@engage.command("close")
@click.argument("engagement_id")
@click.pass_context
def engage_close(ctx: click.Context, engagement_id: str) -> None:
    data = _request(ctx, "POST", f"/engagements/{engagement_id}/close")
    console.print_json(data=data)


@engage.command("erase")
@click.argument("engagement_id")
@click.pass_context
def engage_erase(ctx: click.Context, engagement_id: str) -> None:
    data = _request(ctx, "POST", f"/engagements/{engagement_id}/erase")
    console.print_json(data=data)


@engage.command("list")
@click.pass_context
def engage_list_cmd(ctx: click.Context) -> None:
    data = _request(ctx, "GET", "/engagements")
    table = Table(title="Engagements")
    for col in ("id", "slug", "purpose", "status", "created_at", "closed_at"):
        table.add_column(col)
    for eng in data["engagements"]:
        table.add_row(
            eng["id"],
            eng["slug"],
            eng["purpose"],
            eng["status"],
            str(eng["created_at"]),
            str(eng.get("closed_at") or ""),
        )
    console.print(table)


@engage.command("provision")
@click.argument("engagement_id")
@click.option("--template", required=True, help="Template name to provision from.")
@click.pass_context
def engage_provision(ctx: click.Context, engagement_id: str, template: str) -> None:
    """Provision the engagement's network + VMs from a template."""
    data = _request(
        ctx,
        "POST",
        f"/engagements/{engagement_id}/provision",
        json={"template": template},
    )
    console.print_json(data=data)


@engage.command("teardown")
@click.argument("engagement_id")
@click.pass_context
def engage_teardown(ctx: click.Context, engagement_id: str) -> None:
    """Destroy the engagement's VMs and network. Workspace and audit chain remain."""
    data = _request(ctx, "POST", f"/engagements/{engagement_id}/teardown")
    console.print_json(data=data)


@engage.command("vms")
@click.argument("engagement_id")
@click.pass_context
def engage_vms(ctx: click.Context, engagement_id: str) -> None:
    """List provisioned VMs for an engagement."""
    data = _request(ctx, "GET", f"/engagements/{engagement_id}/vms")
    console.print_json(data=data)


@engage.command("workspace-edit")
@click.argument("engagement_id")
@click.option(
    "--note",
    "note_body",
    default=None,
    help="Inline note body. If omitted, $EDITOR opens an empty buffer.",
)
@click.option(
    "--date",
    "note_date",
    default=None,
    help="Override note date (YYYY-MM-DD). Default: today (UTC).",
)
def engage_workspace_edit(
    engagement_id: str,
    note_body: str | None,
    note_date: str | None,
) -> None:
    """Append a note to the engagement's workspace notes/YYYY-MM-DD.md."""
    from eidolon.orchestrator.lib.workspace import EngagementWorkspace, WorkspaceError

    if note_body is None:
        note_body = click.edit() or ""
    body = note_body.strip()
    if not body:
        click.echo(_json.dumps({"error": "empty_note"}))
        sys.exit(1)
    try:
        path = EngagementWorkspace(engagement_id).write_note(body, date=note_date)
    except WorkspaceError as exc:
        click.echo(_json.dumps({"error": exc.reason}))
        sys.exit(1)
    click.echo(_json.dumps({"status": "ok", "path": str(path)}))


@main.command("run")
@click.argument("tool_id")
@click.option("--engagement-id", required=True)
@click.option("--scope-token", required=True)
@click.option("--action", required=True)
@click.option("--target")
@click.option("--confirm-token")
@click.option("--arg", "args", multiple=True, help="key=value, repeatable")
@click.pass_context
def run_tool(
    ctx: click.Context,
    tool_id: str,
    engagement_id: str,
    scope_token: str,
    action: str,
    target: str | None,
    confirm_token: str | None,
    args: tuple[str, ...],
) -> None:
    parsed_args: dict[str, str] = {}
    for entry in args:
        if "=" not in entry:
            console.print(f"[red]bad arg:[/red] {entry}")
            sys.exit(2)
        key, value = entry.split("=", 1)
        parsed_args[key] = value

    payload: dict[str, Any] = {
        "engagement_id": engagement_id,
        "tool_id": tool_id,
        "action": action,
        "args": parsed_args,
    }
    if target:
        payload["target"] = target
    if confirm_token:
        payload["confirm_token"] = confirm_token

    data = _request(
        ctx,
        "POST",
        "/tools/dispatch",
        json=payload,
        headers={"x-scope-token": scope_token},
    )
    console.print_json(data=data)


@main.command("health")
@click.pass_context
def health(ctx: click.Context) -> None:
    data = _request(ctx, "GET", "/health")
    table = Table(title="Eidolon orchestrator")
    table.add_column("key")
    table.add_column("value")
    for k, v in data.items():
        table.add_row(str(k), str(v))
    console.print(table)


@main.group()
def audit() -> None:
    """Audit chain commands."""


@audit.command("head")
def audit_head() -> None:
    from datetime import datetime

    from eidolon.orchestrator.lib.audit import AuditChain

    chain = AuditChain()
    today = datetime.now(UTC).date()
    seg = chain.segment_path_for(today)
    payload = {
        "head": chain.head(),
        "seq": chain.current_seq(),
        "segment": str(seg),
    }
    click.echo(_json.dumps(payload))


@audit.command("verify")
@click.option(
    "--segment",
    "segment_date",
    default=None,
    help="UTC date (YYYY-MM-DD). Default: today.",
)
def audit_verify(segment_date: str | None) -> None:
    from datetime import date as _date
    from datetime import datetime

    from eidolon.orchestrator.lib.audit import AuditChain

    chain = AuditChain()
    if segment_date:
        day = _date.fromisoformat(segment_date)
    else:
        day = datetime.now(UTC).date()
    seg = chain.segment_path_for(day)
    ok, broken = chain.verify(seg)
    payload = {"ok": ok, "broken_seq": broken, "segment": str(seg)}
    click.echo(_json.dumps(payload))
    if not ok:
        sys.exit(1)


@main.group()
def orchestrator() -> None:
    """Orchestrator host-side commands (run on the box that serves the API)."""


@orchestrator.command("init")
def orchestrator_init() -> None:
    """Generate the bearer token if absent. Idempotent: never overwrites."""
    from eidolon.orchestrator.lib.auth import generate_token, load_token, token_path

    if load_token():
        click.echo(
            _json.dumps(
                {
                    "status": "exists",
                    "token_path": str(token_path()),
                    "hint": "use `eidolon orchestrator rotate-token` to replace.",
                }
            )
        )
        return
    token = generate_token()
    click.echo(
        _json.dumps(
            {
                "status": "created",
                "token_path": str(token_path()),
                "token": token,
                "hint": "save this token; only shown once.",
            }
        )
    )


@orchestrator.command("rotate-token")
def orchestrator_rotate() -> None:
    """Replace the bearer token. Existing CLI sessions break until reconfigured."""
    from eidolon.orchestrator.lib.auth import rotate_token, token_path

    token = rotate_token()
    click.echo(
        _json.dumps(
            {
                "status": "rotated",
                "token_path": str(token_path()),
                "token": token,
            }
        )
    )


@orchestrator.command("start")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
@click.option("--reload", is_flag=True, help="Dev auto-reload (uvicorn --reload).")
def orchestrator_start(host: str, port: int, reload: bool) -> None:
    """Run the FastAPI orchestrator via uvicorn."""
    import uvicorn

    from eidolon.orchestrator.lib.auth import load_or_create_token, token_path

    load_or_create_token()
    click.echo(f"orchestrator token at {token_path()}")
    uvicorn.run(
        "eidolon.orchestrator.app.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@main.group()
def templates() -> None:
    """Template registry commands."""


@templates.command("list")
def templates_list() -> None:
    from eidolon.orchestrator.lib.templates import (
        TemplateValidationError,
        list_templates,
    )

    try:
        items = list_templates()
    except TemplateValidationError as exc:
        click.echo(_json.dumps({"error": exc.reason, "dir": str(exc.template_dir)}))
        sys.exit(1)

    if not items:
        click.echo(_json.dumps({"templates": []}))
        return

    table = Table(title="Templates")
    for col in ("name", "version", "substrates", "vms", "directory"):
        table.add_column(col)
    for loaded in items:
        t = loaded.template
        table.add_row(
            t.name,
            t.version,
            ",".join(t.substrate_support),
            str(len(t.vms)),
            str(loaded.directory),
        )
    console.print(table)


@templates.command("info")
@click.argument("name")
def templates_info(name: str) -> None:
    from eidolon.orchestrator.lib.templates import (
        TemplateValidationError,
        load_template_by_name,
    )

    try:
        loaded = load_template_by_name(name)
    except TemplateValidationError as exc:
        click.echo(_json.dumps({"error": exc.reason, "dir": str(exc.template_dir)}))
        sys.exit(1)

    payload = {
        "directory": str(loaded.directory),
        "workspace_skeleton": str(loaded.workspace_skeleton_path)
        if loaded.workspace_skeleton_path
        else None,
        "skills": str(loaded.skills_path) if loaded.skills_path else None,
        "scripts": {k: str(v) for k, v in loaded.scripts_paths.items()},
        "template": loaded.template.model_dump(),
    }
    click.echo(_json.dumps(payload, default=str))


@main.command("login")
@click.option("--host", required=True, help="Orchestrator base URL, e.g. http://orch:8000/v1")
@click.option("--token", "token_value", required=True, help="Bearer token.")
@click.option(
    "--skills-target",
    type=click.Path(path_type=Path),
    default=None,
    help="Override skills install dir (default: ~/.claude/skills).",
)
@click.option(
    "--no-skills",
    is_flag=True,
    help="Skip installing the eidolon-* Claude Code skills.",
)
def login(
    host: str,
    token_value: str,
    skills_target: Path | None,
    no_skills: bool,
) -> None:
    """Persist host+token to ~/.eidolon/laptop.json and install CC skills."""
    from eidolon.cli.skills_install import install_skills

    cfg_path = _laptop_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(cfg_path.parent, 0o700)
    cfg_path.write_text(_json.dumps({"host": host, "token": token_value}))
    os.chmod(cfg_path, 0o600)

    payload: dict[str, Any] = {"status": "ok", "config": str(cfg_path)}
    if not no_skills:
        installed = install_skills(skills_target)
        payload["skills_installed"] = [
            {"name": s.name, "destination": str(s.destination)} for s in installed
        ]
        payload["mcp_hint"] = "Register MCP server: claude mcp add eidolon eidolon-mcp"
    click.echo(_json.dumps(payload))


@main.group()
def skills() -> None:
    """Claude Code skills bundled with Eidolon."""


@skills.command("install")
@click.option(
    "--target",
    type=click.Path(path_type=Path),
    default=None,
    help="Install dir (default: ~/.claude/skills).",
)
@click.option(
    "--no-overwrite",
    is_flag=True,
    help="Skip skills whose destination directory already exists.",
)
def skills_install_cmd(target: Path | None, no_overwrite: bool) -> None:
    """Copy bundled eidolon-* skills into the operator's CC skills dir."""
    from eidolon.cli.skills_install import install_skills

    installed = install_skills(target, overwrite=not no_overwrite)
    click.echo(
        _json.dumps(
            {
                "installed": [
                    {"name": s.name, "destination": str(s.destination)}
                    for s in installed
                ],
            }
        )
    )


@main.group()
def fork() -> None:
    """Decision-fork commands."""


@fork.command("list")
@click.argument("engagement_id")
@click.option(
    "--status",
    "status_filter",
    type=click.Choice(["open", "approved", "denied", "expired"]),
    default=None,
)
@click.pass_context
def fork_list(
    ctx: click.Context,
    engagement_id: str,
    status_filter: str | None,
) -> None:
    params = f"?status={status_filter}" if status_filter else ""
    data = _request(ctx, "GET", f"/engagements/{engagement_id}/forks{params}")
    table = Table(title=f"Forks for {engagement_id}")
    for col in ("id", "fork_type", "status", "prompt"):
        table.add_column(col)
    for f_ in data["forks"]:
        table.add_row(
            f_["id"],
            f_["fork_type"],
            f_["status"],
            (f_.get("prompt") or "")[:80],
        )
    console.print(table)


@fork.command("show")
@click.argument("engagement_id")
@click.argument("fork_id")
@click.pass_context
def fork_show(
    ctx: click.Context, engagement_id: str, fork_id: str
) -> None:
    data = _request(ctx, "GET", f"/engagements/{engagement_id}/forks")
    for f_ in data["forks"]:
        if f_["id"] == fork_id:
            console.print_json(data=f_)
            return
    click.echo(_json.dumps({"error": "not_found", "fork_id": fork_id}))
    sys.exit(1)


@fork.command("open")
@click.argument("engagement_id")
@click.option(
    "--type",
    "fork_type",
    required=True,
    type=click.Choice(
        [
            "path_selection",
            "mode_change",
            "cred_disposition",
            "noise_threshold",
            "scope_edge",
        ]
    ),
)
@click.option("--prompt", required=True, help="What the operator must decide.")
@click.option("--context", "context_json", default="{}", help="Context dict (JSON).")
@click.pass_context
def fork_open(
    ctx: click.Context,
    engagement_id: str,
    fork_type: str,
    prompt: str,
    context_json: str,
) -> None:
    try:
        ctx_dict = _json.loads(context_json)
    except _json.JSONDecodeError as exc:
        raise click.BadParameter(f"--context must be JSON: {exc}") from exc
    payload = {"fork_type": fork_type, "prompt": prompt, "context": ctx_dict}
    data = _request(
        ctx, "POST", f"/engagements/{engagement_id}/forks", json=payload
    )
    console.print_json(data=data)


@fork.command("resolve")
@click.argument("fork_id")
@click.option(
    "--resolution",
    type=click.Choice(["approved", "denied"]),
    required=True,
)
@click.option("--operator", required=True, help="Operator name attached to the resolution.")
@click.option("--rationale", default="", help="Why the operator chose this.")
@click.pass_context
def fork_resolve(
    ctx: click.Context,
    fork_id: str,
    resolution: str,
    operator: str,
    rationale: str,
) -> None:
    payload = {
        "resolution": resolution,
        "operator": operator,
        "rationale": rationale,
    }
    data = _request(
        ctx, "POST", f"/engagements/forks/{fork_id}/resolve", json=payload
    )
    console.print_json(data=data)


@main.group()
def secrets() -> None:
    """Secrets broker (env / macOS Keychain / 1Password)."""


@secrets.command("backend")
def secrets_backend() -> None:
    """Print the active backend name + availability."""
    from eidolon.orchestrator.lib.secrets import get_backend, reset_backend

    reset_backend()
    backend = get_backend()
    click.echo(
        _json.dumps(
            {"backend": backend.name, "available": backend.available()}
        )
    )


@secrets.command("store")
@click.argument("label")
@click.option("--value", required=False, help="Secret value. If omitted, read from stdin.")
def secrets_store(label: str, value: str | None) -> None:
    """Store a secret under <label>."""
    from eidolon.orchestrator.lib.secrets import SecretsBroker, SecretsError

    if value is None:
        value = sys.stdin.read().rstrip("\n")
    if not value:
        click.echo(_json.dumps({"error": "empty_value"}))
        sys.exit(1)
    try:
        SecretsBroker().put(label, value)
    except SecretsError as exc:
        click.echo(_json.dumps({"error": exc.reason}))
        sys.exit(1)
    click.echo(_json.dumps({"status": "ok", "label": label}))


@secrets.command("get")
@click.argument("label")
def secrets_get(label: str) -> None:
    """Print the secret value for <label> (use carefully)."""
    from eidolon.orchestrator.lib.secrets import SecretsBroker, SecretsError

    try:
        value = SecretsBroker().get(label)
    except SecretsError as exc:
        click.echo(_json.dumps({"error": exc.reason}))
        sys.exit(1)
    if value is None:
        click.echo(_json.dumps({"error": "not_found", "label": label}))
        sys.exit(1)
    click.echo(value)


@secrets.command("list")
def secrets_list() -> None:
    """List secret labels visible to the active backend.

    Only the env backend can enumerate (via EIDOLON_SECRET_* env vars). For
    Keychain and 1Password, label enumeration requires extra ACL plumbing
    that is intentionally out of scope for v0.1; check presence per label
    with `secrets get <label>` instead.
    """
    import os as _os

    from eidolon.orchestrator.lib.secrets import get_backend, reset_backend

    reset_backend()
    backend = get_backend()
    if backend.name != "env":
        click.echo(
            _json.dumps(
                {
                    "backend": backend.name,
                    "labels": None,
                    "hint": "label enumeration not supported on this backend",
                }
            )
        )
        return
    prefix = "EIDOLON_SECRET_"
    labels = sorted(
        k[len(prefix) :].lower() for k in _os.environ if k.startswith(prefix)
    )
    click.echo(_json.dumps({"backend": "env", "labels": labels}))


@secrets.command("revoke")
@click.argument("label")
def secrets_revoke(label: str) -> None:
    """Delete the secret stored under <label>."""
    from eidolon.orchestrator.lib.secrets import SecretsBroker, SecretsError

    try:
        ok = SecretsBroker().delete(label)
    except SecretsError as exc:
        click.echo(_json.dumps({"error": exc.reason}))
        sys.exit(1)
    click.echo(_json.dumps({"status": "ok" if ok else "not_found", "label": label}))


if __name__ == "__main__":
    main()
