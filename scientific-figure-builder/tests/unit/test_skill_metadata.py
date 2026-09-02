"""Skill metadata and directory-naming validation (Phase 1 exit criteria)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL_MD = ROOT / "SKILL.md"

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
EXPECTED_NAME = "scientific-figure-builder"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    _, fm, body = text.split("---\n", 2)
    return yaml.safe_load(fm), body


def test_skill_md_exists() -> None:
    assert SKILL_MD.is_file(), "SKILL.md missing"


def test_frontmatter_has_required_fields() -> None:
    fm, _ = _parse_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    assert "name" in fm, "frontmatter missing name"
    assert "description" in fm, "frontmatter missing description"


def test_skill_name_is_valid() -> None:
    fm, _ = _parse_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    name = fm["name"]
    assert NAME_RE.match(name), f"skill name {name!r} fails naming rules"
    assert 1 <= len(name) <= 64


def test_skill_name_matches_directory() -> None:
    fm, _ = _parse_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    assert fm["name"] == EXPECTED_NAME
    assert ROOT.name == EXPECTED_NAME, "directory name must match skill name"


def test_description_length() -> None:
    fm, _ = _parse_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    desc = fm["description"]
    assert isinstance(desc, str)
    assert 1 <= len(desc) <= 1024, f"description length {len(desc)} out of range"


def test_skill_md_body_is_nonempty_and_concise() -> None:
    _, body = _parse_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    stripped = body.strip()
    assert len(stripped) > 0, "SKILL.md body is empty"
    assert len(stripped) <= 6000, "SKILL.md body exceeds the concise Skill budget"
