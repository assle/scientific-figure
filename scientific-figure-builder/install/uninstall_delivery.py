"""Recoverable, scope-aware Scientific Figure Builder uninstaller."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

for _parent in Path(__file__).resolve().parents:
    if (_parent / "figure_tools").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from figure_tools.install_paths import PathEnvironment, read_active_runtime  # noqa: E402
from figure_tools.install_transaction import install_lock_status  # noqa: E402

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
    install_home: Path | None = None,
    state_home: Path | None = None,
    cache_home: Path | None = None,
    session_home: Path | None = None,
    codex_home: Path,
    project_dir: Path | None = None,
    include_config: bool = False,
    dry_run: bool = False,
    bin_dir: Path | None = None,
    remove_runtime: bool = True,
    remove_opencode: bool = True,
    remove_codex: bool = True,
) -> dict[str, Any]:
    paths = delivery_paths(
        config_home=config_home, data_home=data_home,
        install_home=install_home,
        state_home=state_home,
        cache_home=cache_home,
        session_home=session_home,
        project_dir=project_dir, codex_home=codex_home, bin_dir=bin_dir,
    )
    removed: list[str] = []
    warnings: list[str] = []
    targets: list[Path] = []
    config_candidates: list[Path] = []

    if remove_runtime:
        lock_status = install_lock_status(paths.install_lock_dir)
        if lock_status == "active":
            warnings.append(
                f"runtime uninstall skipped because an install is active: "
                f"{paths.install_lock_dir}"
            )
            remove_runtime = False
        elif lock_status == "orphaned":
            targets.append(paths.install_lock_dir)

    if remove_runtime:
        targets.extend([
            paths.runtime_scope_dir, paths.state_dir, paths.cache_dir, paths.session_dir,
            paths.staging_parent, paths.transaction_backup_parent,
        ])
        if project_dir is None and paths.legacy_runtime_dir is not None:
            targets.append(paths.legacy_runtime_dir)
        if project_dir is None and paths.launcher_file is not None and paths.launcher_file.exists():
            content = paths.launcher_file.read_text(encoding="utf-8", errors="replace")
            if LAUNCHER_MARKER in content:
                targets.append(paths.launcher_file)
            else:
                warnings.append(f"left unrelated launcher untouched: {paths.launcher_file}")

    if remove_opencode:
        targets.extend((paths.skill_dir, paths.command_file))
        if project_dir is None:
            config_candidates.extend(
                config_home / "opencode" / name
                for name in ("opencode.json", "opencode.jsonc")
            )
        else:
            config_candidates.extend([
                project_dir / ".opencode" / "opencode.json",
                project_dir / ".opencode" / "opencode.jsonc",
                paths.config_file,
            ])

    if remove_codex:
        targets.append(paths.codex_skill_dir)
        if project_dir is None:
            config_candidates.append(codex_home / "config.toml")
        else:
            config_candidates.extend([
                project_dir / ".codex" / "config.toml",
                paths.codex_config_file,
            ])

    if project_dir is None:
        if include_config:
            user_config = config_home / NAME / "config.yaml"
            active = read_active_runtime(paths.active_runtime_file)
            credential_runtime = (
                Path(active["runtime_dir"])
                if active is not None and Path(active["runtime_dir"]).is_dir()
                else paths.runtime_dir
            )
            ok, cleanup_warning = cleanup_keyring_credentials(
                user_config, dry_run=dry_run, runtime_dir=credential_runtime,
            )
            if cleanup_warning:
                warnings.append(cleanup_warning)
            if ok:
                targets.append(config_home / NAME)
            else:
                warnings.append("user config was retained because credential cleanup failed")

    for target in dict.fromkeys(targets):
        if remove_path(target, dry_run=dry_run):
            removed.append(str(target))
    for config in dict.fromkeys(config_candidates):
        changed = remove_codex_mcp(config) if config.suffix == ".toml" else remove_opencode_mcp(config)
        if changed:
            removed.append(str(config))
    return {"removed": removed, "warnings": warnings, "dry_run": dry_run}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Uninstall Scientific Figure Builder safely.")
    parser.add_argument("--config", action="store_true", help="also remove global config and its credentials")
    targets = parser.add_mutually_exclusive_group()
    targets.add_argument(
        "--runtime-only", dest="target", action="store_const", const="runtime",
        help="Remove only the Core runtime and CLI.",
    )
    targets.add_argument(
        "--opencode", dest="target", action="store_const", const="opencode",
        help="Remove only the OpenCode Agent integration.",
    )
    targets.add_argument(
        "--codex-legacy", dest="target", action="store_const", const="codex",
        help="Remove only the deprecated manual Codex integration.",
    )
    targets.add_argument(
        "--integrations", dest="target", action="store_const", const="integrations",
        help="Remove both legacy Agent integrations but keep the Core runtime.",
    )
    targets.add_argument(
        "--all", dest="target", action="store_const", const="all",
        help="Remove Core, legacy integrations, Global config, and referenced credentials.",
    )
    parser.set_defaults(target="runtime")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    path_environment = PathEnvironment.from_environ()
    args = build_parser().parse_args(argv)
    remove_runtime = args.target in {"runtime", "all"}
    remove_opencode = args.target in {"opencode", "integrations", "all"}
    remove_codex = args.target in {"codex", "integrations", "all"}
    result = uninstall(
        config_home=path_environment.config_root,
        data_home=path_environment.legacy_data_root,
        install_home=path_environment.install_root,
        state_home=path_environment.state_root,
        cache_home=path_environment.cache_root,
        session_home=path_environment.session_root,
        codex_home=path_environment.codex_home,
        bin_dir=path_environment.launcher_dir,
        project_dir=args.project,
        include_config=args.config or args.target == "all",
        dry_run=args.dry_run,
        remove_runtime=remove_runtime,
        remove_opencode=remove_opencode,
        remove_codex=remove_codex,
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
