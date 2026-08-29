"""Scientific Figure Builder command-line entry.

Usage: python -m figure_tools init [project_dir]
       python -m figure_tools gui
       python -m figure_tools install-gui
       python -m figure_tools --version
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from figure_tools import __version__
from figure_tools.config import initialize_project


USAGE = (
    "usage: python -m figure_tools "
    "init [project_dir] | gui | install-gui | --version"
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {
        "init", "gui", "install-gui", "-h", "--help", "-V", "--version",
    }:
        print(USAGE)
        return 2
    if argv[0] in {"-h", "--help"}:
        print(USAGE)
        return 0
    if argv[0] in {"-V", "--version"}:
        print(f"scientific-figure {__version__}")
        return 0
    if argv[0] == "install-gui":
        from figure_tools.components import install_gui_component

        try:
            root = install_gui_component()
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            print(f"GUI installation failed: {exc}", file=sys.stderr)
            return 1
        print(f"Scientific Figure Builder GUI installed successfully in {root}.")
        return 0
    if argv[0] == "gui":
        # Keep PySide6 out of init/help and all MCP imports.
        from figure_tools.qml_gui import run_gui

        return run_gui(argv[1:])
    project_dir = argv[1] if len(argv) > 1 else "."
    cfg = initialize_project(project_dir)
    print(json.dumps(cfg, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
