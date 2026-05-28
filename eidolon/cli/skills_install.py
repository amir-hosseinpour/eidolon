"""Install bundled Claude Code skills onto the operator's laptop.

Each skill is a directory with a `SKILL.md` file at its root. We copy each
bundled skill directory into the configured target (default
`~/.claude/skills/<skill-name>`).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

BUNDLED_SKILL_NAMES = ("eidolon-core", "eidolon-fork-watcher", "eidolon-engagement")


@dataclass(frozen=True)
class InstalledSkill:
    name: str
    source: Path
    destination: Path


def bundled_skills_root() -> Path:
    return Path(__file__).resolve().parent.parent / "skills_pack"


def default_target_root() -> Path:
    return Path.home() / ".claude" / "skills"


def install_skills(
    target_root: Path | None = None,
    *,
    overwrite: bool = True,
) -> list[InstalledSkill]:
    """Copy each bundled skill directory under target_root.

    Returns the list of installed skills. With overwrite=True (default),
    existing destinations are replaced. With overwrite=False, existing
    destinations are left untouched and skipped.
    """
    target = (target_root or default_target_root()).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    installed: list[InstalledSkill] = []
    src_root = bundled_skills_root()
    for name in BUNDLED_SKILL_NAMES:
        src = src_root / name
        if not (src / "SKILL.md").is_file():
            raise FileNotFoundError(f"missing SKILL.md in bundled skill: {src}")
        dst = target / name
        if dst.exists():
            if not overwrite:
                continue
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        installed.append(InstalledSkill(name=name, source=src, destination=dst))
    return installed
