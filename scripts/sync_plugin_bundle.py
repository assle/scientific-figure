#!/usr/bin/env python3
"""Synchronize generated Native plugin resources from canonical product sources."""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY_ROOT / "scientific-figure-builder"
PLUGIN = (
    REPOSITORY_ROOT
    / "plugins"
    / "scientific-figure-builder"
)
SKILL_DESTINATION = PLUGIN / "skills" / "scientific-figure-builder"


def sync() -> None:
    generated_root = REPOSITORY_ROOT / "plugins"
    if not PLUGIN.is_relative_to(generated_root):
        raise RuntimeError("plugin destination escaped the generated plugin root")
    SKILL_DESTINATION.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE / "SKILL.md", SKILL_DESTINATION / "SKILL.md")
    for name in ("agents", "references", "schemas", "templates"):
        destination = SKILL_DESTINATION / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(SOURCE / name, destination)
    (PLUGIN / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        SOURCE / "figure_tools" / "resources" / "icon.svg",
        PLUGIN / "assets" / "icon.svg",
    )
    project = tomllib.loads((SOURCE / "pyproject.toml").read_text(encoding="utf-8"))
    manifest_path = PLUGIN / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = str(project["project"]["version"])
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    sync()
