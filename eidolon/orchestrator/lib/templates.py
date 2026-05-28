from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

SubstrateName = Literal["docker", "proxmox", "mac", "windows"]


def _default_substrate_support() -> list[SubstrateName]:
    return ["docker"]

ForkType = Literal[
    "path_selection",
    "mode_change",
    "cred_disposition",
    "noise_threshold",
    "scope_edge",
]


class TemplateValidationError(Exception):
    """Raised when a template directory fails schema or filesystem checks."""

    def __init__(self, template_dir: Path, reason: str) -> None:
        super().__init__(f"{template_dir.name}: {reason}")
        self.template_dir = template_dir
        self.reason = reason


class TemplateVM(BaseModel):
    name: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    image: str
    cpu: int = Field(default=2, ge=1, le=32)
    memory_mb: int = Field(default=2048, ge=128, le=131072)
    privileged: bool = False
    capabilities: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cmd: list[str] | None = None
    volumes: list[tuple[str, str]] = Field(default_factory=list)


class TemplateNetwork(BaseModel):
    name: str = Field(..., pattern=r"^[a-zA-Z0-9_\-{}.]+$")
    cidr: str | None = None


class TemplateForkPolicy(BaseModel):
    """Per-fork-type defaults applied at engagement open."""

    type: ForkType
    auto_resolve: bool = False
    default_message: str = ""


class Template(BaseModel):
    name: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    description: str = ""
    substrate_support: list[SubstrateName] = Field(
        default_factory=_default_substrate_support,
        min_length=1,
    )
    network: TemplateNetwork
    vms: list[TemplateVM] = Field(..., min_length=1)
    secrets_required: list[str] = Field(default_factory=list)
    decision_forks: list[TemplateForkPolicy] = Field(default_factory=list)
    workspace_skeleton: str | None = "workspace_skeleton"
    scripts: dict[str, str] = Field(default_factory=dict)
    skills: str | None = "skills"

    @field_validator("vms")
    @classmethod
    def _unique_vm_names(cls, vms: list[TemplateVM]) -> list[TemplateVM]:
        names = [v.name for v in vms]
        if len(names) != len(set(names)):
            raise ValueError("duplicate vm names")
        return vms


class LoadedTemplate(BaseModel):
    """Template + the directory it was loaded from. Paths resolved relative to dir."""

    template: Template
    directory: Path
    workspace_skeleton_path: Path | None = None
    skills_path: Path | None = None
    scripts_paths: dict[str, Path] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise TemplateValidationError(path.parent, f"yaml parse error: {exc}") from exc
    if not isinstance(data, dict):
        raise TemplateValidationError(path.parent, "template.yaml root must be a mapping")
    return data


def _resolve_optional_dir(template_dir: Path, rel: str | None) -> Path | None:
    if rel is None:
        return None
    candidate = template_dir / rel
    if not candidate.exists():
        return None
    if not candidate.is_dir():
        raise TemplateValidationError(template_dir, f"{rel} must be a directory")
    return candidate


def _resolve_scripts(template_dir: Path, scripts: dict[str, str]) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for label, rel in scripts.items():
        candidate = template_dir / rel
        if not candidate.is_file():
            raise TemplateValidationError(
                template_dir, f"script {label!r} not found at {rel}"
            )
        resolved[label] = candidate
    return resolved


def load_template(template_dir: Path) -> LoadedTemplate:
    """Parse and validate a single template directory."""
    template_yaml = template_dir / "template.yaml"
    if not template_yaml.is_file():
        raise TemplateValidationError(template_dir, "missing template.yaml")
    raw = _read_yaml(template_yaml)
    try:
        template = Template.model_validate(raw)
    except ValidationError as exc:
        raise TemplateValidationError(template_dir, f"schema invalid: {exc}") from exc

    if template.name != template_dir.name:
        raise TemplateValidationError(
            template_dir,
            f"template.yaml name={template.name!r} does not match directory {template_dir.name!r}",
        )

    workspace = _resolve_optional_dir(template_dir, template.workspace_skeleton)
    skills = _resolve_optional_dir(template_dir, template.skills)
    scripts = _resolve_scripts(template_dir, template.scripts)

    return LoadedTemplate(
        template=template,
        directory=template_dir,
        workspace_skeleton_path=workspace,
        skills_path=skills,
        scripts_paths=scripts,
    )


def _bundled_templates_root() -> Path:
    # eidolon/orchestrator/lib/templates.py -> ../../templates
    return Path(__file__).resolve().parent.parent.parent / "templates"


def _operator_templates_root() -> Path:
    home = os.environ.get("EIDOLON_HOME")
    base = Path(home) if home else Path.home() / ".eidolon"
    return base / "templates"


def template_search_paths() -> list[Path]:
    """Lookup order: operator installs first, then bundled defaults."""
    return [_operator_templates_root(), _bundled_templates_root()]


def list_templates() -> list[LoadedTemplate]:
    seen: dict[str, LoadedTemplate] = {}
    for root in template_search_paths():
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if (child / "template.yaml").is_file() and child.name not in seen:
                seen[child.name] = load_template(child)
    return list(seen.values())


def load_template_by_name(name: str) -> LoadedTemplate:
    for root in template_search_paths():
        candidate = root / name
        if (candidate / "template.yaml").is_file():
            return load_template(candidate)
    raise TemplateValidationError(
        _operator_templates_root() / name, "template not found"
    )
