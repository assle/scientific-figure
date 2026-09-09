#!/usr/bin/env python3
"""Record observed local convergence for a release candidate."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def acceptance_from_status(
    status: object,
    *,
    confirm_codex_restart: bool,
) -> dict[str, object]:
    if not confirm_codex_restart:
        raise RuntimeError("Codex restart must be explicitly confirmed")
    if not isinstance(status, dict) or status.get("conclusion") != "converged":
        raise RuntimeError("local status is not converged")
    version = status.get("target_version")
    plugin = status.get("plugin")
    if not isinstance(version, str) or not isinstance(plugin, dict):
        raise RuntimeError("local status has no Product version or Native plugin")
    if (
        plugin.get("installed") is not True
        or plugin.get("enabled") is not True
        or plugin.get("version") != version
        or status.get("cli_version") != version
    ):
        raise RuntimeError("Native plugin, Active runtime, and CLI are not converged")
    if status.get("stale_instances") != []:
        raise RuntimeError("old Runtime instances are still running")
    instances = status.get("running_instances")
    if not isinstance(instances, list):
        raise RuntimeError("local status has no Running runtime instances")
    versions: dict[str, str] = {}
    for item in instances:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind in {"mcp", "gui"} and item.get("version") == version:
            versions[str(kind)] = version
    if "mcp" not in versions:
        raise RuntimeError("a new-task MCP instance was not observed")
    if "gui" not in versions:
        raise RuntimeError("the Configuration app was not observed")
    return {
        "product_version": version,
        "codex_restart_verified": True,
        "new_task_mcp_verified": True,
        "plugin_version": version,
        "active_runtime_version": version,
        "cli_version": version,
        "mcp_version": versions["mcp"],
        "configuration_app_version": versions["gui"],
        "old_processes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record release acceptance")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument(
        "--launcher", type=Path,
        default=Path.home() / ".local/bin/scientific-figure",
    )
    parser.add_argument("--status-json", type=Path)
    parser.add_argument("--confirm-codex-restarted", action="store_true")
    args = parser.parse_args(argv)
    if args.status_json is not None:
        status: Any = json.loads(args.status_json.read_text(encoding="utf-8"))
    else:
        completed = subprocess.run(
            [str(args.launcher), "status", "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        status = json.loads(completed.stdout)
    evidence = acceptance_from_status(
        status,
        confirm_codex_restart=args.confirm_codex_restarted,
    )
    destination = (
        args.repository_root / "release-acceptance"
        / f"{evidence['product_version']}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
