"""Maintainer release command behavior."""

from __future__ import annotations

import importlib.util
import json
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
    assert "verify_release_candidate.py --build" in quality_commands
    assert release[True]["push"]["tags"] == ["v*"]
    release_commands = "\n".join(
        str(step.get("run", "")) for step in release["jobs"]["release"]["steps"]
    )
    assert "verify_release_candidate.py --tests --build" in release_commands
    assert "gh release create" in release_commands


def test_publish_requires_real_local_convergence_acceptance(tmp_path: Path) -> None:
    module = _module()
    acceptance = tmp_path / "release-acceptance"
    acceptance.mkdir()
    (acceptance / "0.6.0.json").write_text(json.dumps({
        "product_version": "0.6.0",
        "codex_restart_verified": True,
        "new_task_mcp_verified": True,
        "plugin_version": "0.6.0",
        "active_runtime_version": "0.6.0",
        "cli_version": "0.6.0",
        "mcp_version": "0.6.0",
        "configuration_app_version": "0.6.0",
        "old_processes": 0,
    }))

    module.require_release_acceptance(tmp_path, "0.6.0")
    with pytest.raises(RuntimeError, match="acceptance evidence"):
        module.require_release_acceptance(tmp_path, "0.6.1")


def test_publish_requires_explicitly_approved_release_notes(tmp_path: Path) -> None:
    module = _module()
    notes = tmp_path / "release-notes"
    notes.mkdir()
    path = notes / "0.6.0.md"
    path.write_text("---\nstatus: draft\n---\n\n# Notes\n")

    with pytest.raises(RuntimeError, match="not approved"):
        module.require_approved_release_notes(tmp_path, "0.6.0")
    path.write_text("---\nstatus: approved\n---\n\n# Notes\n")
    module.require_approved_release_notes(tmp_path, "0.6.0")


def test_release_is_complete_only_with_every_formal_artifact() -> None:
    module = _module()
    partial = {
        "url": "https://example.test/release",
        "isDraft": False,
        "assets": [{"name": "SHA256SUMS"}],
    }
    complete = {
        **partial,
        "assets": [
            {"name": "SHA256SUMS"},
            {"name": "scientific-figure-builder-0.6.0.tar.gz"},
            {"name": "scientific_figure_builder-0.6.0-py3-none-any.whl"},
        ],
    }

    assert module.release_is_complete(partial, "0.6.0") is False
    assert module.release_is_complete(complete, "0.6.0") is True


def test_unfinished_current_version_is_resumed_instead_of_bumped_again() -> None:
    module = _module()
    assert module.select_target_version(
        "0.6.0", "minor", current_release_complete=False,
    ) == "0.6.0"
    assert module.select_target_version(
        "0.6.0", "minor", current_release_complete=True,
    ) == "0.7.0"
