from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import eidolon.cli.main as cli_main
from eidolon.cli.skills_install import (
    BUNDLED_SKILL_NAMES,
    bundled_skills_root,
    install_skills,
)


def test_bundled_skills_have_skill_md_with_frontmatter() -> None:
    root = bundled_skills_root()
    for name in BUNDLED_SKILL_NAMES:
        body = (root / name / "SKILL.md").read_text()
        assert body.startswith("---\n"), name
        assert f"name: {name}\n" in body, name
        assert "description:" in body, name


def test_install_skills_copies_three_skills(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    installed = install_skills(target)
    names = [s.name for s in installed]
    assert names == list(BUNDLED_SKILL_NAMES)
    for s in installed:
        assert (s.destination / "SKILL.md").is_file()


def test_install_skills_overwrites_by_default(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    install_skills(target)
    stamp = target / "eidolon-core" / "SKILL.md"
    stamp.write_text("clobber me")
    install_skills(target)
    assert stamp.read_text().startswith("---\n")


def test_install_skills_no_overwrite_skips_existing(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    install_skills(target)
    stamp = target / "eidolon-core" / "SKILL.md"
    stamp.write_text("preserved")
    again = install_skills(target, overwrite=False)
    assert again == []
    assert stamp.read_text() == "preserved"


def test_login_writes_config_and_installs_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    eidolon_home = tmp_path / "home" / ".eidolon"
    monkeypatch.setattr(cli_main, "_laptop_config_path", lambda: eidolon_home / "laptop.json")

    skills_dir = tmp_path / "claude-skills"
    runner = CliRunner()
    result = runner.invoke(
        cli_main.main,
        [
            "login",
            "--host",
            "http://orch:8000/v1",
            "--token",
            "operator-bearer",
            "--skills-target",
            str(skills_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["config"].endswith("laptop.json")
    assert {s["name"] for s in payload["skills_installed"]} == set(BUNDLED_SKILL_NAMES)
    assert "claude mcp add eidolon eidolon-mcp" in payload["mcp_hint"]

    cfg = json.loads((eidolon_home / "laptop.json").read_text())
    assert cfg == {"host": "http://orch:8000/v1", "token": "operator-bearer"}
    for name in BUNDLED_SKILL_NAMES:
        assert (skills_dir / name / "SKILL.md").is_file()


def test_login_no_skills_skips_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    eidolon_home = tmp_path / "home" / ".eidolon"
    monkeypatch.setattr(cli_main, "_laptop_config_path", lambda: eidolon_home / "laptop.json")

    runner = CliRunner()
    result = runner.invoke(
        cli_main.main,
        [
            "login",
            "--host",
            "http://orch:8000/v1",
            "--token",
            "operator-bearer",
            "--no-skills",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "skills_installed" not in payload


def test_skills_install_subcommand(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "skills"
    result = runner.invoke(
        cli_main.main,
        ["skills", "install", "--target", str(target)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert {s["name"] for s in payload["installed"]} == set(BUNDLED_SKILL_NAMES)
    for name in BUNDLED_SKILL_NAMES:
        assert (target / name / "SKILL.md").is_file()
