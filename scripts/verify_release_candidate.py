#!/usr/bin/env python3
"""Run the shared CI checks and optionally build release artifacts."""

from __future__ import annotations

import argparse
import os
import subprocess
import tomllib
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify one release candidate")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--tests", action="store_true")
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args(argv)
    repository = args.repository_root.resolve()
    package = repository / "scientific-figure-builder"
    if args.tests:
        _run(("uv", "run", "--frozen", "pytest"), package)
    _run(("uv", "sync", "--frozen", "--extra", "gui"), package)
    _run((
        "uvx", "pyright", "--pythonpath", ".venv/bin/python",
        "figure_tools", "install", "../scripts",
    ), package)
    if args.build:
        _run(("uv", "build", "--wheel"), package)
        project = tomllib.loads((package / "pyproject.toml").read_text(encoding="utf-8"))
        version = str(project["project"]["version"])
        wheels = sorted(
            (package / "dist").glob(f"scientific_figure_builder-{version}-*.whl")
        )
        if len(wheels) != 1:
            raise RuntimeError("release build must produce exactly one Core wheel")
        source_commit = os.environ.get("GITHUB_SHA") or _capture(
            ("git", "rev-parse", "HEAD"), repository,
        )
        _run((
            "uv", "run", "--frozen", "python", "-m", "figure_tools.release_bundle",
            "--repository-root", str(repository),
            "--output-dir", str(package / "dist"),
            "--core-wheel", str(wheels[0]),
            "--source-commit", source_commit,
        ), package)
    return 0


def _run(command: tuple[str, ...], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _capture(command: tuple[str, ...], cwd: Path) -> str:
    return subprocess.run(
        command, cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
