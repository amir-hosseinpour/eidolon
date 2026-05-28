from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import eidolon.cli.main as cli_main
from eidolon.orchestrator.lib.templates import (
    TemplateValidationError,
    list_templates,
    load_template,
    load_template_by_name,
)

_GOOD_TEMPLATE = """
name: blank-kali
version: "1.0"
description: A bare Kali Linux container for ad-hoc work.
substrate_support: [docker]
network:
  name: "eng-{{engagement_id}}"
  cidr: 10.42.0.0/24
vms:
  - name: kali
    image: kalilinux/kali-rolling:latest
    cpu: 2
    memory_mb: 2048
    capabilities: [NET_ADMIN]
secrets_required: []
decision_forks: []
"""


def _write_template(root: Path, name: str, body: str) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "template.yaml").write_text(body)
    return d


def test_load_valid_template(tmp_path: Path) -> None:
    d = _write_template(tmp_path, "blank-kali", _GOOD_TEMPLATE)
    loaded = load_template(d)
    assert loaded.template.name == "blank-kali"
    assert loaded.template.vms[0].name == "kali"
    assert loaded.directory == d


def test_load_template_optional_dirs_resolve(tmp_path: Path) -> None:
    d = _write_template(tmp_path, "blank-kali", _GOOD_TEMPLATE)
    (d / "workspace_skeleton").mkdir()
    (d / "skills").mkdir()
    loaded = load_template(d)
    assert loaded.workspace_skeleton_path == d / "workspace_skeleton"
    assert loaded.skills_path == d / "skills"


def test_template_name_must_match_directory(tmp_path: Path) -> None:
    d = _write_template(tmp_path, "wrong-dir", _GOOD_TEMPLATE)
    with pytest.raises(TemplateValidationError) as exc:
        load_template(d)
    assert "does not match directory" in exc.value.reason


def test_missing_template_yaml_errors(tmp_path: Path) -> None:
    d = tmp_path / "broken"
    d.mkdir()
    with pytest.raises(TemplateValidationError) as exc:
        load_template(d)
    assert "missing template.yaml" in exc.value.reason


def test_invalid_yaml_errors(tmp_path: Path) -> None:
    d = tmp_path / "blank-kali"
    d.mkdir()
    (d / "template.yaml").write_text(": :\n  not: valid:\nyaml: -:")
    with pytest.raises(TemplateValidationError) as exc:
        load_template(d)
    assert "yaml parse error" in exc.value.reason or "schema invalid" in exc.value.reason


def test_duplicate_vm_names_rejected(tmp_path: Path) -> None:
    body = _GOOD_TEMPLATE + """\
  - name: kali
    image: kalilinux/kali-rolling:latest
"""
    d = _write_template(tmp_path, "blank-kali", body)
    with pytest.raises(TemplateValidationError):
        load_template(d)


def test_missing_script_file_errors(tmp_path: Path) -> None:
    body = _GOOD_TEMPLATE + "scripts:\n  setup: scripts/setup.sh\n"
    d = _write_template(tmp_path, "blank-kali", body)
    with pytest.raises(TemplateValidationError) as exc:
        load_template(d)
    assert "script 'setup'" in exc.value.reason


def test_list_templates_prefers_operator_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = tmp_path / "operator-home" / "templates"
    operator.mkdir(parents=True)
    _write_template(operator, "blank-kali", _GOOD_TEMPLATE)

    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path / "operator-home"))

    items = list_templates()
    names = [i.template.name for i in items]
    assert "blank-kali" in names


def test_load_template_by_name_finds_operator_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = tmp_path / "operator-home" / "templates"
    operator.mkdir(parents=True)
    _write_template(operator, "blank-kali", _GOOD_TEMPLATE)

    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path / "operator-home"))
    loaded = load_template_by_name("blank-kali")
    assert loaded.template.name == "blank-kali"


def test_load_template_by_name_raises_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path / "empty-home"))
    with pytest.raises(TemplateValidationError):
        load_template_by_name("does-not-exist")


def test_cli_templates_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    operator = tmp_path / "operator-home" / "templates"
    operator.mkdir(parents=True)
    _write_template(operator, "blank-kali", _GOOD_TEMPLATE)
    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path / "operator-home"))

    runner = CliRunner()
    result = runner.invoke(cli_main.main, ["templates", "list"])
    assert result.exit_code == 0, result.output
    assert "blank-kali" in result.output


def test_cli_templates_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    operator = tmp_path / "operator-home" / "templates"
    operator.mkdir(parents=True)
    _write_template(operator, "blank-kali", _GOOD_TEMPLATE)
    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path / "operator-home"))

    runner = CliRunner()
    result = runner.invoke(cli_main.main, ["templates", "info", "blank-kali"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["template"]["name"] == "blank-kali"
    assert body["template"]["vms"][0]["name"] == "kali"


def test_bundled_blank_kali_loads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bundled blank-kali template ships valid and loadable."""
    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path / "empty-home"))
    loaded = load_template_by_name("blank-kali")
    assert loaded.template.name == "blank-kali"
    assert loaded.template.substrate_support == ["docker"]
    assert any(vm.name == "kali" for vm in loaded.template.vms)
    assert "bootstrap" in loaded.scripts_paths
    assert loaded.scripts_paths["bootstrap"].is_file()
    assert loaded.workspace_skeleton_path is not None
    assert loaded.workspace_skeleton_path.is_dir()
    assert loaded.skills_path is not None
    assert loaded.skills_path.is_dir()


def test_bundled_web_app_pentest_loads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bundled web-app-pentest template ships valid and loadable."""
    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path / "empty-home"))
    loaded = load_template_by_name("web-app-pentest")
    assert loaded.template.name == "web-app-pentest"
    assert loaded.template.substrate_support == ["docker"]
    assert any(vm.name == "kali" for vm in loaded.template.vms)
    fork_types = {f.type for f in loaded.template.decision_forks}
    assert {"scope_edge", "noise_threshold", "cred_disposition"}.issubset(fork_types)
    assert "bootstrap" in loaded.scripts_paths
    assert "install_tools" in loaded.scripts_paths
    assert loaded.scripts_paths["bootstrap"].is_file()
    assert loaded.scripts_paths["install_tools"].is_file()


def test_bundled_ad_recon_single_loads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bundled ad-recon-single template ships valid and loadable."""
    monkeypatch.setenv("EIDOLON_HOME", str(tmp_path / "empty-home"))
    loaded = load_template_by_name("ad-recon-single")
    assert loaded.template.name == "ad-recon-single"
    assert loaded.template.substrate_support == ["proxmox"]
    assert any(vm.name == "kali-ad" for vm in loaded.template.vms)
    assert "ad_credentials" in loaded.template.secrets_required
    fork_types = {f.type for f in loaded.template.decision_forks}
    assert {
        "scope_edge",
        "noise_threshold",
        "cred_disposition",
        "mode_change",
    }.issubset(fork_types)
    assert "bootstrap" in loaded.scripts_paths
