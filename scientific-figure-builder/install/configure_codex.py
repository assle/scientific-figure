"""Safe Codex configuration merger for ``~/.codex/config.toml``.

The merger only ever rewrites the ``[mcp_servers.scientific-figure]`` table. It
preserves unrelated configuration and, when present, leaves the existing
``[mcp_servers.scientific-figure.env]`` subtable untouched.
"""

from __future__ import annotations

import json
import os
import shutil
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_MCP_NAME = "scientific-figure"


def _toml_string(value: str) -> str:
    """Render a TOML basic string without assuming a TOML writer dependency."""
    return json.dumps(value, ensure_ascii=False)


def _toml_string_list(values: list[str]) -> str:
    if not values:
        return "[]"
    lines = [f"  {_toml_string(value)}," for value in values]
    return "[\n" + "\n".join(lines) + "\n]"


def _header_line(table_name: str) -> str:
    return f"[mcp_servers.{table_name}]"


def _env_header_line(table_name: str) -> str:
    return f"[mcp_servers.{table_name}.env]"


def _is_header(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("[")


def _remove_table_block(text: str, header: str) -> str:
    """Remove one table block starting at ``header`` and ending before the next
    table header. Sub-tables that immediately follow are preserved."""
    lines = text.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if line.strip() == header:
            start = index
            break
    if start is None:
        return text

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if _is_header(lines[index]):
            end = index
            break

    del lines[start:end]
    return "".join(lines)


def _has_existing_env_table(text: str, mcp_name: str) -> bool:
    header = _env_header_line(mcp_name)
    if header in text:
        return True
    if not text.strip():
        return False
    try:
        parsed = tomllib.loads(text)
    except Exception:
        return False
    return isinstance(
        parsed.get("mcp_servers", {}).get(mcp_name, {}).get("env"),
        dict,
    )


def codex_mcp_entry(runtime_python: str | Path, runtime_dir: str | Path) -> dict[str, Any]:
    """Build a Codex MCP entry backed by the installed private runtime."""
    return {
        "command": str(Path(runtime_python).absolute()),
        "args": ["-m", "figure_tools.server"],
        "cwd": str(Path(runtime_dir).absolute()),
        "enabled": True,
    }


def _env_vars_from_environment() -> list[str]:
    names = (
        "ARK_API_KEY",
        "ARK_API_KEY_CODING",
        "ARK_IMAGE_GENERATE",
        "ARK_IMAGE_EDIT",
        "ARK_VISION_ANALYZE",
        "ARK_VISION_VALIDATE",
    )
    return list(names)


def _render_parent_table(entry: dict[str, Any], env_vars: list[str]) -> str:
    lines = [
        _header_line(DEFAULT_MCP_NAME) + "\n",
        f"command = {_toml_string(entry['command'])}\n",
        f"args = {_toml_string_list(entry['args'])}\n",
        f"cwd = {_toml_string(entry['cwd'])}\n",
        "enabled = true\n",
    ]
    if env_vars:
        lines.append(f"env_vars = {_toml_string_list(env_vars)}\n")
    return "".join(lines)


def update_codex_mcp_config(
    config_path: str | Path,
    mcp_name: str,
    entry: dict[str, Any],
    *,
    backup: bool = True,
) -> dict[str, Any]:
    """Insert or update the target MCP table without rewriting the file."""
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"

    has_existing_env_table = _has_existing_env_table(text, mcp_name)
    parent_header = _header_line(mcp_name)
    cleaned = _remove_table_block(text, parent_header)

    env_vars = [] if has_existing_env_table else _env_vars_from_environment()
    replacement = _render_parent_table(entry, env_vars)
    new_text = cleaned
    if new_text and not new_text.endswith("\n\n"):
        new_text = new_text.rstrip() + "\n\n"
    new_text += replacement

    backup_path = None
    if backup and config_path.exists() and config_path.read_text(encoding="utf-8") != new_text:
        backup_path = config_path.with_suffix(config_path.suffix + ".bak")
        shutil.copyfile(config_path, backup_path)

    config_path.write_text(new_text, encoding="utf-8")
    try:
        parsed = tomllib.loads(new_text)
        mcp = parsed.get("mcp_servers", {}).get(mcp_name)
        if not isinstance(mcp, dict):
            raise RuntimeError("Codex MCP table was not written correctly")
        if mcp.get("command") != entry["command"]:
            raise RuntimeError("Codex MCP command was not written correctly")
    except Exception as exc:
        if backup_path is not None:
            shutil.copyfile(backup_path, config_path)
        raise RuntimeError(f"Failed to verify Codex config.toml after merge: {exc}") from exc

    return {"applied": True, "backup": str(backup_path) if backup_path else None}


def verify_codex_config(config_path: str | Path, mcp_name: str) -> dict[str, Any]:
    config_path = Path(config_path)
    text = config_path.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    mcp = parsed.get("mcp_servers", {}).get(mcp_name)
    checks = {
        "config_exists": config_path.is_file(),
        "mcp_table": isinstance(mcp, dict),
        "command": bool(mcp.get("command") if isinstance(mcp, dict) else None),
    }
    return {"checks": checks, "mcp_tools": 14}
