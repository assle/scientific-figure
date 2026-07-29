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
import re
import shutil
from pathlib import Path
from typing import Any, Callable

DEFAULT_MCP_NAME = "scientific-figure"


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    return text


def load_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    text = _strip_comments(p.read_text(encoding="utf-8"))
    if not text.strip():
        return {}
    return json.loads(text)


def dump_config(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def propose_merge(existing: dict[str, Any], mcp_name: str,
                  mcp_entry: dict[str, Any]) -> dict[str, Any]:
    proposed = copy.deepcopy(existing)
    proposed.setdefault("mcp", {})
    proposed["mcp"][mcp_name] = copy.deepcopy(mcp_entry)
    return proposed


def render_diff(existing: dict[str, Any], proposed: dict[str, Any]) -> str:
    a = dump_config(existing).splitlines(keepends=True)
    b = dump_config(proposed).splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, fromfile="opencode.json", tofile="opencode.json"))


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

    if approver is not None and not approver(diff):
        return {"applied": False, "diff": diff, "backup": None}

    backup_path = None
    if backup and config_path.exists():
        backup_path = config_path.with_suffix(config_path.suffix + ".bak")
        shutil.copyfile(config_path, backup_path)

    config_path.write_text(dump_config(proposed), encoding="utf-8")
    return {"applied": True, "diff": diff, "backup": str(backup_path) if backup_path else None}


def mcp_entry_for(package_dir: str | Path) -> dict[str, Any]:
    """Build the local MCP server entry that launches the bundled server via uv.

    The server reads Ark credentials/model IDs from the environment (user-local
    private config, plan section 5); these references are expanded by OpenCode
    from the user's shell environment. No secret values are stored in the config.
    """
    return {
        "type": "local",
        "command": ["uv", "run", "--directory", str(package_dir),
                     "python", "-m", "figure_tools.server"],
        "enabled": True,
        "environment": {
            "ARK_API_KEY": "{env:ARK_API_KEY}",
            "ARK_API_KEY_CODING": "{env:ARK_API_KEY_CODING}",
            "ARK_IMAGE_GENERATE": "{env:ARK_IMAGE_GENERATE}",
            "ARK_IMAGE_EDIT": "{env:ARK_IMAGE_EDIT}",
            "ARK_VISION_ANALYZE": "{env:ARK_VISION_ANALYZE}",
            "ARK_VISION_VALIDATE": "{env:ARK_VISION_VALIDATE}",
        },
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
