#!/usr/bin/env python3
"""Launch the active Scientific Figure Builder Core runtime for Codex."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Mapping


APP_NAME = "scientific-figure-builder"
WINDOWS_APP_DIR = "ScientificFigureBuilder"
INSTALL_COMMAND = "./install.sh --codex"


def install_root(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
    platform_name: str | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    explicit = env.get("SCIENTIFIC_FIGURE_INSTALL_HOME")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            raise RuntimeError("SCIENTIFIC_FIGURE_INSTALL_HOME must be an absolute path")
        return path
    resolved_home = (home or Path.home()).expanduser().absolute()
    platform = platform_name or os.name
    if platform == "nt":
        local = Path(env.get("LOCALAPPDATA", resolved_home / "AppData" / "Local"))
        return local / "Programs" / WINDOWS_APP_DIR
    return resolved_home / ".local" / "lib" / APP_NAME


def active_runtime(root: Path) -> Path:
    metadata_path = root / "global" / "active-runtime.json"
    if not metadata_path.is_file():
        raise RuntimeError(
            "Scientific Figure Builder Core runtime is not installed. "
            f"From the source repository, run: {INSTALL_COMMAND}"
        )
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        runtime = Path(data["runtime_dir"]).absolute()
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid active runtime metadata: {metadata_path}") from exc
    try:
        runtime.relative_to(root.absolute())
    except ValueError as exc:
        raise RuntimeError("active runtime points outside the installation prefix") from exc
    if not runtime.is_dir():
        raise RuntimeError(
            f"active Core runtime is missing: {runtime}; rerun {INSTALL_COMMAND}"
        )
    return runtime


def runtime_python(runtime: Path) -> Path:
    candidates = (
        runtime / ".venv" / "bin" / "python",
        runtime / ".venv" / "Scripts" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"active Core runtime has no private Python: {runtime}")


def main() -> int:
    try:
        runtime = active_runtime(install_root())
        python = runtime_python(runtime)
    except RuntimeError as exc:
        print(f"Scientific Figure Builder MCP startup failed: {exc}", file=sys.stderr)
        return 1
    os.chdir(runtime)
    os.execve(
        str(python),
        [str(python), "-m", "figure_tools.server"],
        dict(os.environ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
