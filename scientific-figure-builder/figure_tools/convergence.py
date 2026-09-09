"""Local version-convergence cleanup for installed Runtime startup."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Iterable

from figure_tools.install_paths import (
    PathEnvironment,
    global_active_runtime_file,
    native_plugin_cache_dir,
    read_active_runtime,
    resolve_delivery_paths,
)
from figure_tools.install_transaction import prune_runtime_versions
from figure_tools.local_status import RunningRuntimeInstance, discover_running_runtime_instances


def cleanup_local_versions(
    environment: PathEnvironment,
    *,
    running_instances: Iterable[RunningRuntimeInstance] | None = None,
) -> tuple[Path, ...]:
    """Remove superseded product files only after process convergence."""

    active = read_active_runtime(global_active_runtime_file(environment))
    if active is None or not active.get("version"):
        return ()
    target = active["version"]
    selected = tuple(
        discover_running_runtime_instances(environment) if running_instances is None else running_instances
    )
    if any(process.version not in {None, target} for process in selected):
        return ()
    paths = resolve_delivery_paths(environment, target)
    removed = [Path(path) for path in prune_runtime_versions(paths, None)]
    plugin_root = native_plugin_cache_dir(environment)
    if plugin_root.is_dir():
        for candidate in plugin_root.iterdir():
            if candidate.name == target or not candidate.is_dir():
                continue
            shutil.rmtree(candidate)
            removed.append(candidate)
    return tuple(removed)


def cleanup_from_installed_runtime() -> tuple[Path, ...]:
    """Run convergence cleanup only from an installed product interpreter."""

    environment = PathEnvironment.from_environ()
    try:
        Path(sys.executable).absolute().relative_to(environment.install_root.absolute())
    except (OSError, ValueError):
        return ()
    return cleanup_local_versions(environment)


__all__ = ["cleanup_from_installed_runtime", "cleanup_local_versions"]
