#!/bin/sh
set -eu

# One-command uninstaller for Scientific Figure Builder.
#
# Reverses what ./install.sh adds: removes the private runtime, the installed
# Codex & OpenCode skills, the OpenCode slash command, and the
# "mcp.scientific-figure" / "[mcp_servers.scientific-figure]" entries. It never
# touches this repository or unrelated configuration.
#
# Usage:
#   ./uninstall.sh                  # remove the global installation
#   ./uninstall.sh --config         # also remove ~/.config/scientific-figure-builder/
#   ./uninstall.sh --project DIR    # remove a per-project install in DIR
#   ./uninstall.sh --all            # global + user config
#   ./uninstall.sh --dry-run        # print what would be removed, change nothing
#   ./uninstall.sh --help

REPOSITORY_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -f "$REPOSITORY_DIR/scientific-figure-builder/install.sh" ]; then
  python3 - "$@" <<'PY'
import argparse, json, os, re, shutil, sys
from pathlib import Path

home = Path.home()
data_home = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))

NAME = "scientific-figure-builder"
MCP = "scientific-figure"


def remove_dir(p):
    if p.exists() and p.is_dir():
        shutil.rmtree(p)
        return True
    return False


def remove_file(p):
    if p.is_file():
        p.unlink()
        return True
    return False


def remove_opencode_mcp(config_path):
    """Drop {"mcp":{"scientific-figure":...}} from an OpenCode config, keeping the rest."""
    if not config_path.is_file():
        return False
    raw = config_path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
    text = re.sub(r"(^|\s)//.*$", "", text, flags=re.M)
    try:
        data = json.loads(text)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    removed = data.get("mcp", {}).pop(MCP, None)
    if removed is None:
        return False
    # Preserve the key order of the original where possible; write compact JSON.
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def remove_codex_mcp(config_path):
    """Drop the [mcp_servers.scientific-figure] table (and its env sub-table)."""
    if not config_path.is_file():
        return False
    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if l.strip() == f"[mcp_servers.{MCP}]"), None)
    if start is None:
        return False
    end = len(lines)
    for i in range(start + 1, len(lines)):
        s = lines[i].lstrip()
        if s.startswith("["):
            name = s.strip().strip("[").strip("]")
            if not name.startswith(f"mcp_servers.{MCP}"):
                end = i
                break
    del lines[start:end]
    config_path.write_text("".join(lines), encoding="utf-8")
    return True


def has_opencode_mcp(config_path):
    if not config_path.is_file():
        return False
    raw = config_path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
    text = re.sub(r"(^|\s)//.*$", "", text, flags=re.M)
    try:
        data = json.loads(text)
    except Exception:
        return False
    return isinstance(data, dict) and isinstance(data.get("mcp"), dict) and MCP in data["mcp"]


def has_codex_mcp(config_path):
    if not config_path.is_file():
        return False
    return any(l.strip() == f"[mcp_servers.{MCP}]" for l in config_path.read_text(encoding="utf-8").splitlines())


def opencode_config_files():
    base = config_home / "opencode"
    for name in ("opencode.json", "opencode.jsonc"):
        p = base / name
        if p.is_file():
            yield p


def project_config_files(project_dir):
    opencode = project_dir / ".opencode"
    for name in ("opencode.json", "opencode.jsonc"):
        p = opencode / name
        if p.is_file():
            yield p
    codex = project_dir / ".codex"
    p = codex / "config.toml"
    if p.is_file():
        yield p


def build_plan(include_config, project_dirs):
    plan = {
        "dirs": [],
        "files": [],
        "configs": [],
    }
    # Global runtime
    plan["dirs"].append(data_home / NAME)
    # OpenCode global skill + command
    plan["dirs"].append(config_home / "opencode" / "skills" / NAME)
    plan["files"].append(config_home / "opencode" / "commands" / f"{MCP}.md")
    # Codex global skill
    plan["dirs"].append(codex_home / "skills" / NAME)
    # OpenCode + Codex MCP entries (global)
    plan["configs"].extend(list(opencode_config_files()))
    plan["configs"].append(codex_home / "config.toml")
    # User config dir
    if include_config:
        plan["dirs"].append(config_home / NAME)
    # Per-project installs
    for project_dir in project_dirs:
        plan["dirs"].append(project_dir / ".opencode" / "skills" / NAME)
        plan["files"].append(project_dir / ".opencode" / "commands" / f"{MCP}.md")
        plan["dirs"].append(project_dir / ".codex" / "skills" / NAME)
        plan["configs"].extend(list(project_config_files(project_dir)))
    # Dedupe, keep order
    seen = set()
    for key in list(plan):
        unique = []
        for item in plan[key]:
            p = str(item)
            if p not in seen:
                seen.add(p)
                unique.append(item)
        plan[key] = unique
    return plan


def main():
    parser = argparse.ArgumentParser(description="Uninstall Scientific Figure Builder.")
    parser.add_argument("--config", action="store_true", help="also remove the user config dir")
    parser.add_argument("--project", action="append", type=Path, default=[], help="remove a per-project install")
    parser.add_argument("--all", action="store_true", help="global + user config")
    parser.add_argument("--dry-run", action="store_true", help="print what would be removed, change nothing")
    args = parser.parse_args()

    include_config = args.config or args.all
    plan = build_plan(include_config, args.project)

    removed_dirs, removed_files, removed_configs = [], [], []
    for p in plan["dirs"]:
        if not args.dry_run and p.exists():
            remove_dir(p)
            removed_dirs.append(p)
        elif args.dry_run and p.exists():
            removed_dirs.append(p)
    for p in plan["files"]:
        if not args.dry_run and p.exists():
            remove_file(p)
            removed_files.append(p)
        elif args.dry_run and p.exists():
            removed_files.append(p)
    for p in plan["configs"]:
        is_toml = p.suffix == ".toml"
        if args.dry_run:
            present = has_codex_mcp(p) if is_toml else has_opencode_mcp(p)
            if present:
                removed_configs.append(p)
        else:
            ok = remove_codex_mcp(p) if is_toml else remove_opencode_mcp(p)
            if ok:
                removed_configs.append(p)

    if args.dry_run:
        print("Dry run — nothing changed. Would remove:")
    else:
        print("Uninstall complete. Removed:")
    for p in removed_dirs:
        print("  dir   ", p)
    for p in removed_files:
        print("  file  ", p)
    for p in removed_configs:
        print("  config", p)
    if not removed_dirs and not removed_files and not removed_configs:
        print("  (nothing found to remove)")


if __name__ == "__main__":
    main()
PY
else
  echo "This must be run from a checkout of scientific-figure (missing scientific-figure-builder/)." >&2
  exit 1
fi
