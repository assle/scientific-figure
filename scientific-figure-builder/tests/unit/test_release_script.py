"""Maintainer release command behavior."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "release.py"


def _module():
    spec = importlib.util.spec_from_file_location("scientific_figure_release", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("current", "selector", "expected"),
    [
        ("0.5.1", "patch", "0.5.2"),
        ("0.5.1", "minor", "0.6.0"),
        ("0.5.1", "major", "1.0.0"),
        ("0.5.1", "0.6.0", "0.6.0"),
    ],
)
def test_release_selector_resolves_one_target_version(
    current: str, selector: str, expected: str
) -> None:
    assert _module().resolve_target_version(current, selector) == expected


def test_release_refuses_to_move_an_existing_tag() -> None:
    with pytest.raises(RuntimeError, match="immutable tag"):
        _module().require_tag_target(
            tag="v0.6.0", actual="old-commit", expected="new-commit",
        )


def test_ci_owns_quality_bundle_and_tag_release_workflows() -> None:
    ci_text = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    release_text = (
        REPOSITORY_ROOT / ".github" / "workflows" / "release.yml"
    ).read_text()
    ci = yaml.safe_load(ci_text)
    release = yaml.safe_load(release_text)

    assert "quality" in ci["jobs"]
    quality_commands = "\n".join(
        str(step.get("run", "")) for step in ci["jobs"]["quality"]["steps"]
    )
    assert "pyright" in quality_commands
    assert "release_bundle" in quality_commands
    assert release[True]["push"]["tags"] == ["v*"]
    release_commands = "\n".join(
        str(step.get("run", "")) for step in release["jobs"]["release"]["steps"]
    )
    assert "gh release create" in release_commands
