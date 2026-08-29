"""Product-version consistency across package and release metadata."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

from figure_tools import __version__


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PACKAGE_ROOT.parent
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def _product_version() -> str:
    data = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _skill_metadata() -> dict:
    text = (PACKAGE_ROOT / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter, _ = text.split("---\n", 2)
    return yaml.safe_load(frontmatter)["metadata"]


def test_canonical_product_version_is_semver() -> None:
    assert SEMVER.fullmatch(_product_version())


def test_installed_runtime_reads_canonical_product_version() -> None:
    assert __version__ == _product_version()


def test_release_metadata_mirrors_product_version() -> None:
    expected = _product_version()
    citation = yaml.safe_load(
        (REPOSITORY_ROOT / "CITATION.cff").read_text(encoding="utf-8")
    )
    assert str(_skill_metadata()["version"]) == expected
    assert str(citation["version"]) == expected


def test_readmes_publish_current_development_version() -> None:
    expected = _product_version()
    for name in ("README.md", "README.zh-CN.md"):
        assert expected in (REPOSITORY_ROOT / name).read_text(encoding="utf-8")
