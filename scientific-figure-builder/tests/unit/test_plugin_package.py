"""Native Codex plugin manifest, generated Skill, and MCP Adapter contract."""

from __future__ import annotations

import importlib.util
import json
import tomllib
from pathlib import Path

import pytest

from figure_tools.install_paths import PathEnvironment


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PACKAGE_ROOT.parent
PLUGIN_ROOT = (
    REPOSITORY_ROOT
    / "plugins"
    / "scientific-figure-builder"
)
MARKETPLACE = REPOSITORY_ROOT / ".agents" / "plugins" / "marketplace.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _launcher_module():
    path = PLUGIN_ROOT / "scripts" / "mcp_launcher.py"
    spec = importlib.util.spec_from_file_location("scientific_figure_mcp_launcher", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plugin_manifest_identifies_complete_product() -> None:
    manifest = _json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["name"] == PLUGIN_ROOT.name == "scientific-figure-builder"
    assert manifest["version"] == project["project"]["version"]
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["interface"]["displayName"] == "Scientific Figure Builder"
    assert manifest["interface"]["defaultPrompt"]


def test_repo_marketplace_resolves_plugin_source() -> None:
    marketplace = _json(MARKETPLACE)
    assert marketplace["name"] == "scientific-figure"
    entry = next(
        item for item in marketplace["plugins"]
        if item["name"] == "scientific-figure-builder"
    )
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    assert (REPOSITORY_ROOT / entry["source"]["path"]).resolve() == PLUGIN_ROOT


def test_plugin_mcp_uses_bundled_adapter_not_user_codex_config() -> None:
    mcp = _json(PLUGIN_ROOT / ".mcp.json")["mcpServers"]["scientific-figure"]
    assert mcp["command"] == "uv"
    assert mcp["args"] == [
        "run", "python", "./scripts/mcp_launcher.py",
    ]
    assert mcp["cwd"] == "."
    assert "SCIENTIFIC_FIGURE_INSTALL_HOME" in mcp["env_vars"]


def test_generated_plugin_skill_matches_canonical_sources() -> None:
    destination = PLUGIN_ROOT / "skills" / "scientific-figure-builder"
    for name in ("SKILL.md", "agents", "references", "schemas", "templates"):
        source = PACKAGE_ROOT / name
        target = destination / name
        if source.is_file():
            assert target.read_bytes() == source.read_bytes()
            continue
        source_files = {
            path.relative_to(source): path.read_bytes()
            for path in source.rglob("*") if path.is_file()
        }
        target_files = {
            path.relative_to(target): path.read_bytes()
            for path in target.rglob("*") if path.is_file()
        }
        assert target_files == source_files


@pytest.mark.parametrize("platform_name", ["posix", "nt"])
def test_plugin_adapter_uses_canonical_install_prefix(
    tmp_path: Path, platform_name: str,
) -> None:
    launcher = _launcher_module()
    environ = {}
    assert launcher.install_root(
        environ, home=tmp_path, platform_name=platform_name,
    ) == PathEnvironment.from_environ(
        environ, home=tmp_path, platform_name=platform_name,
    ).install_root


def test_plugin_adapter_missing_runtime_is_actionable(tmp_path: Path) -> None:
    launcher = _launcher_module()
    with pytest.raises(RuntimeError, match="./install.sh --runtime-only"):
        launcher.active_runtime(tmp_path)


def test_plugin_adapter_rejects_runtime_outside_install_prefix(tmp_path: Path) -> None:
    launcher = _launcher_module()
    active = tmp_path / "global" / "active-runtime.json"
    active.parent.mkdir(parents=True)
    active.write_text(
        json.dumps({"runtime_dir": str(tmp_path.parent / "outside")}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="outside the installation prefix"):
        launcher.active_runtime(tmp_path)
