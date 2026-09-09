"""Read-only local Product-version convergence status."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping

from figure_tools.install_paths import PathEnvironment, read_active_runtime
from figure_tools.install_paths import resolve_delivery_paths
from figure_tools.install_transaction import prune_runtime_versions


@dataclass(frozen=True)
class PluginInstallation:
    installed: bool
    enabled: bool
    version: str | None


@dataclass(frozen=True)
class LocalProcess:
    pid: int
    parent_pid: int
    kind: str
    version: str | None
    executable: Path


@dataclass(frozen=True)
class LocalStatusRequest:
    environment: PathEnvironment
    cli_version: str
    published_version: str | None = None
    require_plugin: bool = True


PLUGIN_NAME = "scientific-figure-builder"
PLUGIN_MARKETPLACE = "scientific-figure"


@dataclass(frozen=True)
class LocalStatusResult:
    conclusion: str
    exit_code: int
    target_version: str | None
    active_runtime: Path | None
    cli_version: str
    published_version: str | None
    plugin: PluginInstallation
    processes: tuple[LocalProcess, ...]
    stale_processes: tuple[int, ...]
    in_use_runtimes: tuple[Path, ...]
    retained_runtimes: tuple[Path, ...]
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["active_runtime"] = (
            str(self.active_runtime) if self.active_runtime is not None else None
        )
        payload["in_use_runtimes"] = [str(path) for path in self.in_use_runtimes]
        payload["retained_runtimes"] = [str(path) for path in self.retained_runtimes]
        payload["processes"] = [
            {**asdict(process), "executable": str(process.executable)}
            for process in self.processes
        ]
        return payload


def collect_local_status(
    request: LocalStatusRequest,
    *,
    plugin: PluginInstallation,
    processes: Iterable[LocalProcess],
) -> LocalStatusResult:
    """Return one local status result without changing installation state."""

    try:
        active = read_active_runtime(
            request.environment.install_root / "global" / "active-runtime.json"
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _broken(request, plugin, tuple(processes), str(exc))
    if active is None:
        return _broken(request, plugin, tuple(processes), "active runtime is missing")

    target_version = active.get("version")
    runtime_text = active.get("runtime_dir")
    if not target_version or not runtime_text:
        return _broken(request, plugin, tuple(processes), "active runtime is invalid")
    active_runtime = Path(runtime_text)
    if not active_runtime.is_dir():
        return _broken(request, plugin, tuple(processes), "active runtime is missing")

    selected_processes = tuple(processes)
    stale = tuple(
        process.pid
        for process in selected_processes
        if process.version is not None and process.version != target_version
    )
    in_use = tuple(dict.fromkeys(
        process.executable.parents[2]
        for process in selected_processes
        if process.executable.name.startswith("python")
        and len(process.executable.parents) >= 3
        and process.executable.parents[2] != active_runtime
    ))
    runtime_root = active_runtime.parent
    retained = tuple(
        path for path in sorted(runtime_root.iterdir())
        if path.is_dir() and path != active_runtime
    ) if runtime_root.is_dir() else ()

    inconsistent = (
        request.cli_version != target_version
        or (
            request.require_plugin
            and (
                not plugin.installed
                or not plugin.enabled
                or plugin.version != target_version
            )
        )
    )
    if inconsistent:
        conclusion, exit_code = "inconsistent", 3
    elif stale:
        conclusion, exit_code = "restart_required", 2
    elif (
        request.published_version is not None
        and request.published_version != target_version
    ):
        conclusion, exit_code = "update_available", 3
    else:
        conclusion, exit_code = "converged", 0
    return LocalStatusResult(
        conclusion=conclusion,
        exit_code=exit_code,
        target_version=target_version,
        active_runtime=active_runtime,
        cli_version=request.cli_version,
        published_version=request.published_version,
        plugin=plugin,
        processes=selected_processes,
        stale_processes=stale,
        in_use_runtimes=in_use,
        retained_runtimes=retained,
    )


def status_from_system(
    cli_version: str,
    *,
    environ: Mapping[str, str] | None = None,
    published_version: str | None = None,
) -> LocalStatusResult:
    """Inspect the current user's installation without starting MCP or GUI."""

    environment_values = os.environ if environ is None else environ
    environment = PathEnvironment.from_environ(environment_values)
    plugin = _installed_codex_plugin(environment_values)
    opencode_skill = (
        environment.config_root / "opencode" / "skills"
        / "scientific-figure-builder" / "SKILL.md"
    )
    return collect_local_status(
        LocalStatusRequest(
            environment=environment,
            cli_version=cli_version,
            published_version=published_version,
            require_plugin=plugin.installed or not opencode_skill.is_file(),
        ),
        plugin=plugin,
        processes=discover_product_processes(environment),
    )


def render_human_status(result: LocalStatusResult, *, verbose: bool = False) -> str:
    """Render a compact local status while keeping user paths readable."""

    plugin_version = result.plugin.version or "not installed"
    lines = [
        "Scientific Figure Builder local status",
        f"  Conclusion:      {result.conclusion}",
        f"  Target version:  {result.target_version or 'unknown'}",
        f"  Latest release:  {result.published_version or 'not checked'}",
        f"  Native plugin:   {plugin_version}",
        f"  Active runtime:  {_display_path(result.active_runtime)}",
        f"  CLI:             {result.cli_version}",
        f"  Running MCP:     {sum(item.kind == 'mcp' for item in result.processes)}",
        f"  Running GUI:     {sum(item.kind == 'gui' for item in result.processes)}",
        f"  Stale processes: {len(result.stale_processes)}",
    ]
    if result.error:
        lines.append(f"  Error:           {result.error}")
    if verbose:
        for process in result.processes:
            lines.append(
                f"  PID {process.pid}: {process.kind} {process.version or 'unknown'} "
                f"{_display_path(process.executable)}"
            )
        for runtime in result.retained_runtimes:
            lines.append(f"  Retained:        {_display_path(runtime)}")
    return "\n".join(lines)


def _installed_codex_plugin(environ: Mapping[str, str]) -> PluginInstallation:
    codex = shutil.which("codex", path=environ.get("PATH"))
    if codex is None:
        macos = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
        codex = str(macos) if macos.is_file() else None
    if codex is None:
        return PluginInstallation(False, False, None)
    completed = subprocess.run(
        [codex, "plugin", "list", "--marketplace", PLUGIN_MARKETPLACE, "--json"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=dict(environ),
    )
    if completed.returncode != 0:
        return PluginInstallation(False, False, None)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return PluginInstallation(False, False, None)
    for item in payload.get("installed", []):
        if item.get("name") == PLUGIN_NAME:
            return PluginInstallation(
                bool(item.get("installed")),
                bool(item.get("enabled")),
                str(item["version"]) if item.get("version") is not None else None,
            )
    return PluginInstallation(False, False, None)


def discover_product_processes(environment: PathEnvironment) -> tuple[LocalProcess, ...]:
    import psutil

    result: list[LocalProcess] = []
    install_root = environment.install_root.resolve()
    for process in psutil.process_iter(("pid", "ppid", "exe", "cmdline")):
        try:
            info = process.info
            executable_text = info.get("exe")
            command = [str(item) for item in (info.get("cmdline") or [])]
            if not executable_text:
                continue
            executable = Path(str(executable_text)).resolve()
            try:
                executable.relative_to(install_root)
            except ValueError:
                continue
            kind = _process_kind(command)
            if kind is None:
                continue
            result.append(LocalProcess(
                pid=int(info["pid"]),
                parent_pid=int(info.get("ppid") or 0),
                kind=kind,
                version=_runtime_version(executable, install_root),
                executable=executable,
            ))
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            continue
    return tuple(sorted(result, key=lambda item: item.pid))


def cleanup_local_versions(
    environment: PathEnvironment,
    *,
    processes: Iterable[LocalProcess] | None = None,
) -> tuple[Path, ...]:
    """Remove superseded product files only after process convergence."""

    active_file = environment.install_root / "global" / "active-runtime.json"
    active = read_active_runtime(active_file)
    if active is None or not active.get("version"):
        return ()
    target = active["version"]
    selected = tuple(
        discover_product_processes(environment) if processes is None else processes
    )
    if any(process.version not in {None, target} for process in selected):
        return ()
    paths = resolve_delivery_paths(environment, target)
    removed = [Path(path) for path in prune_runtime_versions(paths, None)]
    plugin_root = (
        environment.codex_home / "plugins" / "cache" / "scientific-figure"
        / "scientific-figure-builder"
    )
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
        Path(sys.executable).resolve().relative_to(environment.install_root.resolve())
    except (OSError, ValueError):
        return ()
    return cleanup_local_versions(environment)


def _process_kind(command: list[str]) -> str | None:
    joined = " ".join(command)
    if "figure_tools.server" in joined:
        return "mcp"
    if "figure_tools gui" in joined:
        return "gui"
    return None


def _runtime_version(executable: Path, install_root: Path) -> str | None:
    try:
        relative = executable.relative_to(install_root)
    except ValueError:
        return None
    parts = relative.parts
    try:
        index = parts.index("runtimes")
        return parts[index + 1]
    except (ValueError, IndexError):
        return None


def _display_path(path: Path | None) -> str:
    if path is None:
        return "missing"
    home = Path.home()
    try:
        return str(Path("~") / path.resolve().relative_to(home.resolve()))
    except (OSError, ValueError):
        return str(path)


def _broken(
    request: LocalStatusRequest,
    plugin: PluginInstallation,
    processes: tuple[LocalProcess, ...],
    error: str,
) -> LocalStatusResult:
    return LocalStatusResult(
        conclusion="broken",
        exit_code=4,
        target_version=None,
        active_runtime=None,
        cli_version=request.cli_version,
        published_version=request.published_version,
        plugin=plugin,
        processes=processes,
        stale_processes=(),
        in_use_runtimes=(),
        retained_runtimes=(),
        error=error,
    )


__all__ = [
    "LocalProcess",
    "LocalStatusRequest",
    "LocalStatusResult",
    "PluginInstallation",
    "collect_local_status",
    "cleanup_local_versions",
    "cleanup_from_installed_runtime",
    "discover_product_processes",
    "render_human_status",
    "status_from_system",
]
