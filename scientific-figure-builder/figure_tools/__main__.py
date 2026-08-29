"""Scientific Figure Builder command-line entry.

Usage: python -m figure_tools init [project_dir]
       python -m figure_tools gui
       python -m figure_tools --version
"""

from __future__ import annotations

import json
import sys
from typing import Any

from figure_tools import __version__
from figure_tools.config import initialize_project


USAGE = "usage: python -m figure_tools init [project_dir] | gui | --version"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {
        "init", "gui", "-h", "--help", "-V", "--version",
    }:
        print(USAGE)
        return 2
    if argv[0] in {"-h", "--help"}:
        print(USAGE)
        return 0
    if argv[0] in {"-V", "--version"}:
        print(f"scientific-figure {__version__}")
        return 0
    if argv[0] == "gui":
        # Keep PySide6 out of init/help and all MCP imports.
        from figure_tools.gui import run_gui

        return run_gui(argv[1:])
    project_dir = argv[1] if len(argv) > 1 else "."
    cfg = initialize_project(project_dir)
    print(json.dumps(cfg, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
