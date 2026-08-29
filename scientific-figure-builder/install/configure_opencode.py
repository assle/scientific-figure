"""Safe OpenCode configuration merger (plan section 14).

1. Inspect existing configuration.
2. Generate a proposed merged configuration.
3. Show the diff.
4. Ask for approval.
5. Back up the original file.
6. Preserve all unrelated providers, MCP servers, and permissions.

The merger only ever touches the `mcp.<our-name>` entry. It is tested against
temp files and never the user's real config during development.
"""

from __future__ import annotations

import copy
import difflib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

for _parent in Path(__file__).resolve().parents:
    if (_parent / "figure_tools").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from figure_tools.jsonc_edit import load_jsonc, set_mcp_entry  # noqa: E402

try:
    from .provider_environment import PROVIDER_ENV_VARS
except ImportError:  # Direct execution from install.sh.
    from provider_environment import PROVIDER_ENV_VARS

DEFAULT_MCP_NAME = "scientific-figure"
OPENCODE_SCHEMA = "https://opencode.ai/config.json"


def load_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    return load_jsonc(text)


def dump_config(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def propose_merge(existing: dict[str, Any], mcp_name: str,
                  mcp_entry: dict[str, Any]) -> dict[str, Any]:
    proposed = copy.deepcopy(existing)
    proposed.setdefault("$schema", OPENCODE_SCHEMA)
    proposed.setdefault("mcp", {})
    proposed["mcp"][mcp_name] = copy.deepcopy(mcp_entry)
    return proposed


def render_diff(existing: dict[str, Any], proposed: dict[str, Any]) -> str:
    a = dump_config(existing).splitlines(keepends=True)
    b = dump_config(proposed).splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, fromfile="opencode.json", tofile="opencode.json"))


def render_mcp_merge(text: str, mcp_name: str, mcp_entry: dict[str, Any]) -> str:
    """Render a comment-preserving candidate without writing the config."""

    return set_mcp_entry(text, mcp_name, mcp_entry)


def apply_merge(
    config_path: str | Path,
    mcp_name: str,
    mcp_entry: dict[str, Any],
    approver: Callable[[str], bool] | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    config_path = Path(config_path)
    existing = load_config(config_path)
    proposed = propose_merge(existing, mcp_name, mcp_entry)
    diff = render_diff(existing, proposed)
    original_text = (
        config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    )
    candidate_text = render_mcp_merge(original_text, mcp_name, mcp_entry)

    if approver is not None and not approver(diff):
        return {"applied": False, "diff": diff, "backup": None}

    backup_path = None
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if backup and config_path.exists():
        backup_path = config_path.with_suffix(config_path.suffix + ".bak")
        shutil.copyfile(config_path, backup_path)

    config_path.write_text(candidate_text, encoding="utf-8")
    try:
        verified = load_config(config_path)
        if verified.get("mcp", {}).get(mcp_name) != mcp_entry:
            raise RuntimeError("OpenCode MCP candidate was not written correctly")
    except Exception:
        if backup_path is not None:
            shutil.copyfile(backup_path, config_path)
        elif config_path.exists():
            config_path.unlink()
        raise
    return {"applied": True, "diff": diff, "backup": str(backup_path) if backup_path else None}


def _mcp_environment() -> dict[str, str]:
    return {name: f"{{env:{name}}}" for name in PROVIDER_ENV_VARS}


def mcp_entry_for_python(runtime_python: str | Path) -> dict[str, Any]:
    """Build an MCP entry backed by an installed, self-contained runtime."""
    # Preserve the virtual-environment launcher instead of resolving its symlink
    # to the bare base interpreter, which would lose installed dependencies.
    python_path = os.path.abspath(os.fspath(runtime_python))
    return {
        "type": "local",
        "command": [python_path, "-m", "figure_tools.server"],
        "enabled": True,
        "environment": _mcp_environment(),
    }


def mcp_entry_for(package_dir: str | Path) -> dict[str, Any]:
    """Build the local MCP server entry that launches the bundled server via uv.

    The server reads provider credentials from the system credential store or
    the environment (user-local private config, plan section 5). No secret
    values are stored in the config.
    """
    return {
        "type": "local",
        "command": ["uv", "run", "--directory", str(package_dir),
                     "python", "-m", "figure_tools.server"],
        "enabled": True,
        "environment": _mcp_environment(),
    }


def main() -> int:
    import sys

    if len(sys.argv) < 2:
        print("usage: configure_opencode.py <opencode-config-path> [package-dir]")
        return 2
    config_path = Path(sys.argv[1])
    package_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent
    entry = mcp_entry_for(package_dir)

    def _approve(diff: str) -> bool:
        print("Proposed change:\n" + diff)
        return input("Apply? [y/N] ").strip().lower() in ("y", "yes")

    result = apply_merge(config_path, DEFAULT_MCP_NAME, entry, approver=_approve, backup=True)
    print("applied" if result["applied"] else "not applied")
    return 0 if result["applied"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
