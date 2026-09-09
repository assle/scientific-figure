"""Read-only local Product-version convergence status."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping

from figure_tools.install_paths import (
    PathEnvironment,
    global_active_runtime_file,
    read_active_runtime,
)


@dataclass(frozen=True)
class PluginInstallation:
    installed: bool
    enabled: bool
    version: str | None


@dataclass(frozen=True)
class RunningRuntimeInstance:
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
    running_instances: tuple[RunningRuntimeInstance, ...]
    stale_instances: tuple[int, ...]
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
        payload["running_instances"] = [
            {**asdict(process), "executable": str(process.executable)}
            for process in self.running_instances
        ]
        return payload


def collect_local_status(
    request: LocalStatusRequest,
    *,
    plugin: PluginInstallation,
    running_instances: Iterable[RunningRuntimeInstance],
) -> LocalStatusResult:
    """Return one local status result without changing installation state."""

    try:
        active = read_active_runtime(
            global_active_runtime_file(request.environment)
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _broken(request, plugin, tuple(running_instances), str(exc))
    if active is None:
        return _broken(request, plugin, tuple(running_instances), "active runtime is missing")

    target_version = active.get("version")
    runtime_text = active.get("runtime_dir")
    if not target_version or not runtime_text:
        return _broken(request, plugin, tuple(running_instances), "active runtime is invalid")
    active_runtime = Path(runtime_text)
    if not active_runtime.is_dir():
        return _broken(request, plugin, tuple(running_instances), "active runtime is missing")

    selected_instances = tuple(running_instances)
    stale = tuple(
        process.pid
        for process in selected_instances
        if process.version is not None and process.version != target_version
    )
    in_use = tuple(dict.fromkeys(
        process.executable.parents[2]
        for process in selected_instances
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
        running_instances=selected_instances,
        stale_instances=stale,
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
    codex_expected = _codex_plugin_expected(environment)
    return collect_local_status(
        LocalStatusRequest(
            environment=environment,
            cli_version=cli_version,
            published_version=published_version,
            require_plugin=codex_expected,
        ),
        plugin=plugin,
        running_instances=discover_running_runtime_instances(environment),
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
        f"  Running MCP:     {sum(item.kind == 'mcp' for item in result.running_instances)}",
        f"  Running GUI:     {sum(item.kind == 'gui' for item in result.running_instances)}",
        f"  Stale running_instances: {len(result.stale_instances)}",
    ]
    if result.error:
        lines.append(f"  Error:           {result.error}")
    if verbose:
        for process in result.running_instances:
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


def _codex_plugin_expected(environment: PathEnvironment) -> bool:
    config = environment.codex_home / "config.toml"
    if not config.is_file():
        return False
    try:
        payload = tomllib.loads(config.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    plugin = (payload.get("plugins") or {}).get(
        "scientific-figure-builder@scientific-figure"
    )
    return isinstance(plugin, dict) and plugin.get("enabled") is True


def discover_running_runtime_instances(environment: PathEnvironment) -> tuple[RunningRuntimeInstance, ...]:
    import psutil

    result: list[RunningRuntimeInstance] = []
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
            result.append(RunningRuntimeInstance(
                pid=int(info["pid"]),
                parent_pid=int(info.get("ppid") or 0),
                kind=kind,
                version=_runtime_version(executable, install_root),
                executable=executable,
            ))
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            continue
    return tuple(sorted(result, key=lambda item: item.pid))


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
    running_instances: tuple[RunningRuntimeInstance, ...],
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
        running_instances=running_instances,
        stale_instances=(),
        in_use_runtimes=(),
        retained_runtimes=(),
        error=error,
    )


__all__ = [
    "RunningRuntimeInstance",
    "LocalStatusRequest",
    "LocalStatusResult",
    "PluginInstallation",
    "collect_local_status",
    "discover_running_runtime_instances",
    "render_human_status",
    "status_from_system",
]
