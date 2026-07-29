"""Command-line entry: project initialization (plan section 14).

Usage: python -m figure_tools init [project_dir]
"""

from __future__ import annotations

import json
import sys
from typing import Any

from figure_tools.config import initialize_project


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {"init", "-h", "--help"}:
        print("usage: python -m figure_tools init [project_dir]")
        return 2
    if argv[0] in {"-h", "--help"}:
        print("usage: python -m figure_tools init [project_dir]")
        return 0
    project_dir = argv[1] if len(argv) > 1 else "."
    cfg = initialize_project(project_dir)
    print(json.dumps(cfg, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
