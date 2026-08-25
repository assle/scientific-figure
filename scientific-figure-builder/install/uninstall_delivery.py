"""Recoverable, scope-aware Scientific Figure Builder uninstaller."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any

try:
    from .auth_cleanup import cleanup_keyring_credentials
    from .install_delivery import LAUNCHER_MARKER, delivery_paths
except ImportError:  # direct execution
    from auth_cleanup import cleanup_keyring_credentials
    from install_delivery import LAUNCHER_MARKER, delivery_paths

NAME = "scientific-figure-builder"
MCP = "scientific-figure"


def _strip_jsonc(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"^\s*//.*$", "", text, flags=re.M)


def remove_opencode_mcp(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    except Exception:
        return False
    if not isinstance(data, dict) or not isinstance(data.get("mcp"), dict):
        return False
    if MCP not in data["mcp"]:
        return False
    del data["mcp"][MCP]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def remove_codex_mcp(path: Path) -> bool:
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines)
                  if line.strip() == f"[mcp_servers.{MCP}]"), None)
    if start is None:
        return False
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("["):
            end = i
            break
    del lines[start:end]
    path.write_text("".join(lines), encoding="utf-8")
    return True


def _credential_ids(config_path: Path) -> list[str]:
    if not config_path.is_file():
        return []
    try:
        import yaml

        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    providers = data.get("providers", {}) if isinstance(data, dict) else {}
    if not isinstance(providers, dict):
        return []
    return sorted({
        str(provider["credential_id"])
        for provider in providers.values()
        if isinstance(provider, dict) and provider.get("credential_id")
    })


def remove_path(path: Path, *, dry_run: bool) -> bool:
    if not path.exists():
        return False
    if not dry_run:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return True


def uninstall(
    *,
    config_home: Path,
    data_home: Path,
    codex_home: Path,
    project_dir: Path | None = None,
    include_config: bool = False,
    dry_run: bool = False,
    bin_dir: Path | None = None,
) -> dict[str, Any]:
    paths = delivery_paths(
        config_home=config_home, data_home=data_home,
        project_dir=project_dir, codex_home=codex_home, bin_dir=bin_dir,
    )
    removed: list[str] = []
    warnings: list[str] = []
    if project_dir is None:
        targets = [
            paths.runtime_dir, paths.skill_dir, paths.command_file,
            paths.codex_skill_dir,
        ]
        if paths.launcher_file is not None and paths.launcher_file.exists():
            content = paths.launcher_file.read_text(encoding="utf-8", errors="replace")
            if LAUNCHER_MARKER in content:
                targets.append(paths.launcher_file)
            else:
                warnings.append(f"left unrelated launcher untouched: {paths.launcher_file}")
        config_candidates = [config_home / "opencode" / name for name in ("opencode.json", "opencode.jsonc")]
        config_candidates.append(codex_home / "config.toml")
        if include_config:
            user_config = config_home / NAME / "config.yaml"
            ok, cleanup_warning = cleanup_keyring_credentials(
                user_config, dry_run=dry_run,
            )
            if cleanup_warning:
                warnings.append(cleanup_warning)
            if ok:
                targets.append(config_home / NAME)
            else:
                warnings.append("user config was retained because credential cleanup failed")
    else:
        targets = [paths.skill_dir, paths.command_file, paths.codex_skill_dir]
        config_candidates = [
            project_dir / ".opencode" / name for name in ("opencode.json", "opencode.jsonc")
        ] + [project_dir / ".codex" / "config.toml"]

    for target in targets:
        if remove_path(target, dry_run=dry_run):
            removed.append(str(target))
    for config in config_candidates:
        changed = remove_codex_mcp(config) if config.suffix == ".toml" else remove_opencode_mcp(config)
        if changed:
            removed.append(str(config))
    return {"removed": removed, "warnings": warnings, "dry_run": dry_run}


def main(argv: list[str] | None = None) -> int:
    home = Path.home()
    parser = argparse.ArgumentParser(description="Uninstall Scientific Figure Builder safely.")
    parser.add_argument("--config", action="store_true", help="also remove global config and its credentials")
    parser.add_argument("--all", action="store_true", help="global uninstall plus config")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = uninstall(
        config_home=Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")),
        data_home=Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")),
        codex_home=Path(os.environ.get("CODEX_HOME", home / ".codex")),
        project_dir=args.project,
        include_config=args.config or args.all,
        dry_run=args.dry_run,
    )
    print("Dry run — nothing changed." if args.dry_run else "Uninstall complete.")
    for path in result["removed"]:
        print("  removed", path)
    for warning in result["warnings"]:
        print("  warning", warning, file=sys.stderr)
    if not result["removed"]:
        print("  (nothing found to remove)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
