"""Scientific Figure Builder command-line entry.

Usage: python -m figure_tools init [project_dir]
       python -m figure_tools gui
       python -m figure_tools install-gui
       python -m figure_tools status [--json] [--verbose] [--remote]
       python -m figure_tools update (--latest|--release VERSION|--bundle FILE)
       python -m figure_tools --version
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from figure_tools import __version__
from figure_tools.config import initialize_project


USAGE = (
    "usage: python -m figure_tools "
    "init [project_dir] | gui | install-gui | status [--json] [--verbose] [--remote] | "
    "update (--latest|--release VERSION|--bundle FILE) [--codex|--opencode] | --version"
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {
        "init", "gui", "install-gui", "status", "update", "-h", "--help", "-V", "--version",
    }:
        print(USAGE)
        return 2
    if argv[0] in {"-h", "--help"}:
        print(USAGE)
        return 0
    if argv[0] in {"-V", "--version"}:
        print(f"scientific-figure {__version__}")
        return 0
    if argv[0] == "status":
        options = set(argv[1:])
        if not options <= {"--json", "--verbose", "--remote"}:
            print(USAGE)
            return 2
        from figure_tools.local_status import render_human_status, status_from_system

        published_version = None
        if "--remote" in options:
            try:
                from figure_tools.providers.github_releases import GitHubReleaseClient

                tag = GitHubReleaseClient().describe("latest").tag_name
                published_version = tag[1:] if tag.startswith("v") else tag
            except (OSError, RuntimeError, ValueError) as exc:
                print(f"Remote status failed: {exc}", file=sys.stderr)
                return 4
        result = status_from_system(
            __version__, published_version=published_version,
        )
        if "--json" in options:
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(render_human_status(result, verbose="--verbose" in options))
        return result.exit_code
    if argv[0] == "update":
        return _run_update(argv[1:])
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


def _run_update(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="scientific-figure update")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bundle", type=Path)
    source.add_argument("--release")
    source.add_argument("--latest", action="store_true")
    hosts = parser.add_mutually_exclusive_group()
    hosts.add_argument("--codex", action="store_const", dest="host", const="codex")
    hosts.add_argument("--opencode", action="store_const", dest="host", const="opencode")
    hosts.add_argument("--all", action="store_const", dest="host", const="all")
    hosts.add_argument(
        "--runtime-only", action="store_const", dest="host", const="runtime",
    )
    parser.set_defaults(host=None)
    gui = parser.add_mutually_exclusive_group()
    gui.add_argument("--with-gui", action="store_true", dest="with_gui")
    gui.add_argument("--without-gui", action="store_false", dest="with_gui")
    parser.set_defaults(with_gui=None)
    parser.add_argument("--json", action="store_true")
    downloaded_release: Path | None = None
    try:
        args = parser.parse_args(argv)
        from figure_tools.activation import (
            ActivationRequest,
            activate_local,
            detect_installed_host,
            preserve_gui_selection,
        )
        from figure_tools.install_paths import PathEnvironment, release_cache_dir
        from figure_tools.release_source import resolve_release_bundle

        environment = PathEnvironment.from_environ()
        expected_version = None
        bundle = args.bundle
        if bundle is not None and not bundle.is_absolute():
            caller_cwd = Path(
                os.environ.get("SCIENTIFIC_FIGURE_CALLER_CWD", os.getcwd())
            )
            bundle = (caller_cwd / bundle).resolve()
        if bundle is None:
            selector = "latest" if args.latest else str(args.release)
            resolved = resolve_release_bundle(
                selector,
                cache_dir=release_cache_dir(environment),
            )
            bundle = resolved.bundle
            expected_version = resolved.version
            downloaded_release = bundle.parent
        result = activate_local(ActivationRequest(
            bundle=bundle,
            environment=environment,
            expected_version=expected_version,
            host=args.host or detect_installed_host(environment),
            with_gui=(
                preserve_gui_selection() if args.with_gui is None else args.with_gui
            ),
        ))
    except (OSError, RuntimeError, ValueError) as exc:
        if downloaded_release is not None:
            shutil.rmtree(downloaded_release, ignore_errors=True)
        print(f"Update failed: {exc}", file=sys.stderr)
        return 1
    if downloaded_release is not None:
        shutil.rmtree(downloaded_release, ignore_errors=True)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"Scientific Figure Builder {result.product_version} activated.")
        print(f"  Active runtime: {result.active_runtime}")
        print(f"  Status:         {result.conclusion.value}")
        print(f"  Clean files:    {'yes' if result.clean else 'no'}")
        if result.cleanup_error:
            print(f"  Cleanup warning: {result.cleanup_error}")
        if result.conclusion == "restart_required":
            print("  Next action:    restart Codex/OpenCode after saving active work")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
