"""One-command installer for the Scientific Figure Builder Agent integration bundle.

The installer keeps secrets out of files. It installs a private runtime,
publishes the Skill and slash command to OpenCode's discovery directories,
installs the Skill for Codex, merges MCP entries into both configuration files
without replacing unrelated configuration, and verifies the installed Core
runtime before reporting success. The optional Configuration app is installed
only when explicitly requested.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
import uuid
from dataclasses import dataclass, replace
from pathlib import Path, PurePath
from typing import Callable, Protocol, Sequence

from figure_tools.install_paths import (
    DeliveryPaths,
    PathEnvironment,
    active_runtime_metadata,
    active_runtime_matches,
    read_active_runtime,
    resolve_delivery_paths,
)
from figure_tools.install_transaction import (
    InstallTransaction,
    prune_runtime_versions,
)

from install.configure_opencode import (
    DEFAULT_MCP_NAME,
    load_config,
    mcp_entry_for_python,
    render_mcp_merge,
)
from install.configure_codex import (
    codex_mcp_entry,
    render_codex_mcp_config,
    verify_codex_config,
)

SKILL_NAME = "scientific-figure-builder"
RUNTIME_ITEMS = (
    "figure_tools",
    "schemas",
    "templates",
    "references",
    "commands",
    "install/install_delivery.py",
    "install/uninstall_delivery.py",
    "install/auth_cleanup.py",
    "install/configure_opencode.py",
    "install/configure_codex.py",
    "install/provider_environment.py",
    "install.sh",
    "SKILL.md",
    "pyproject.toml",
    "uv.lock",
    "LICENSE",
)
SKILL_ITEMS = ("SKILL.md", "references", "schemas", "templates")
COMMAND_SOURCE = Path("commands") / "scientific-figure.md"


@dataclass(frozen=True)
class InstallRequest:
    source_dir: Path
    paths: DeliveryPaths
    target: str
    scope: str
    product_version: str
    with_gui: bool = False

    def __post_init__(self) -> None:
        if self.target not in {"runtime", "opencode", "codex-legacy", "both"}:
            raise ValueError(f"unsupported delivery target: {self.target}")
        if self.scope not in {"global", "project"}:
            raise ValueError(f"unsupported delivery scope: {self.scope}")
        if self.product_version != self.paths.product_version:
            raise ValueError("Install Request Product version does not match delivery paths")
        expected_scope = "global" if self.paths.scope_id == "global" else "project"
        if self.scope != expected_scope:
            raise ValueError("Install Request scope does not match delivery paths")

    @property
    def install_opencode(self) -> bool:
        return self.target in {"opencode", "both"}

    @property
    def install_codex(self) -> bool:
        return self.target in {"codex-legacy", "both"}


@dataclass(frozen=True)
class InstallResult:
    runtime: Path
    runtime_python: Path
    launcher: Path | None
    launcher_warning: str | None
    skill: Path
    command: Path
    config: Path
    codex_skill: Path
    codex_config: Path
    mcp_tools: int
    gui_installed: bool
    active_runtime: dict[str, str]
    transaction_id: str
    transaction_log: Path
    committed_paths: tuple[str, ...]
    retained_paths: tuple[Path, ...]
    pruned_paths: tuple[Path, ...]
    legacy_runtime_retained: Path | None
    runtime_backup: Path | None


@dataclass(frozen=True)
class StagedHostPath:
    staged: Path
    destination: Path
    stage: str


class HostDeliveryAdapter(Protocol):
    """One real host-specific delivery implementation."""

    def preflight(self, paths: DeliveryPaths) -> None: ...

    def targets(self, paths: DeliveryPaths) -> tuple[Path, ...]: ...

    def stage(
        self,
        transaction: InstallTransaction,
        source_dir: Path,
        paths: DeliveryPaths,
        runtime_python_path: Path,
    ) -> tuple[StagedHostPath, ...]: ...


class OpenCodeDeliveryAdapter:
    def preflight(self, paths: DeliveryPaths) -> None:
        load_config(paths.config_file)

    def targets(self, paths: DeliveryPaths) -> tuple[Path, ...]:
        return paths.skill_dir, paths.command_file, paths.config_file

    def stage(
        self,
        transaction: InstallTransaction,
        source_dir: Path,
        paths: DeliveryPaths,
        runtime_python_path: Path,
    ) -> tuple[StagedHostPath, ...]:
        skill = transaction.stage_path("opencode-skill")
        _copy_selected(source_dir, skill, SKILL_ITEMS)
        command = transaction.stage_path("opencode-command.md")
        shutil.copy2(source_dir / COMMAND_SOURCE, command)
        existing_text = (
            paths.config_file.read_text(encoding="utf-8")
            if paths.config_file.exists()
            else ""
        )
        config = _write_staged_text(
            transaction.stage_path("opencode-config.json"),
            render_mcp_merge(
                existing_text,
                DEFAULT_MCP_NAME,
                mcp_entry_for_python(runtime_python_path),
            ),
        )
        return (
            StagedHostPath(skill, paths.skill_dir, "opencode_skill"),
            StagedHostPath(command, paths.command_file, "opencode_command"),
            StagedHostPath(config, paths.config_file, "opencode_config"),
        )


class LegacyCodexDeliveryAdapter:
    def preflight(self, paths: DeliveryPaths) -> None:
        if paths.codex_config_file.exists():
            text = paths.codex_config_file.read_text(encoding="utf-8")
            if text.strip():
                tomllib.loads(text)

    def targets(self, paths: DeliveryPaths) -> tuple[Path, ...]:
        return paths.codex_skill_dir, paths.codex_config_file

    def stage(
        self,
        transaction: InstallTransaction,
        source_dir: Path,
        paths: DeliveryPaths,
        runtime_python_path: Path,
    ) -> tuple[StagedHostPath, ...]:
        skill = transaction.stage_path("codex-skill")
        _copy_selected(source_dir, skill, SKILL_ITEMS)
        existing_text = (
            paths.codex_config_file.read_text(encoding="utf-8")
            if paths.codex_config_file.exists()
            else ""
        )
        config = _write_staged_text(
            transaction.stage_path("codex-config.toml"),
            render_codex_mcp_config(
                existing_text,
                DEFAULT_MCP_NAME,
                codex_mcp_entry(runtime_python_path, paths.runtime_dir),
            ),
        )
        return (
            StagedHostPath(skill, paths.codex_skill_dir, "codex_skill"),
            StagedHostPath(config, paths.codex_config_file, "codex_config"),
        )


def host_delivery_adapters(request: InstallRequest) -> tuple[HostDeliveryAdapter, ...]:
    adapters: list[HostDeliveryAdapter] = []
    if request.install_opencode:
        adapters.append(OpenCodeDeliveryAdapter())
    if request.install_codex:
        adapters.append(LegacyCodexDeliveryAdapter())
    return tuple(adapters)


def read_product_version(source_dir: Path | None = None) -> str:
    root = source_dir or Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(project["project"]["version"])


def default_path_environment() -> PathEnvironment:
    return PathEnvironment.from_environ()


def delivery_paths(
    *,
    config_home: Path | None = None,
    data_home: Path | None = None,
    state_home: Path | None = None,
    cache_home: Path | None = None,
    session_home: Path | None = None,
    install_home: Path | None = None,
    project_dir: Path | None = None,
    codex_home: Path | None = None,
    bin_dir: Path | None = None,
    product_version: str | None = None,
    environment: PathEnvironment | None = None,
) -> DeliveryPaths:
    resolved = environment or default_path_environment()
    overrides: dict[str, Path] = {}
    if config_home is not None:
        overrides["config_root"] = config_home.expanduser().absolute()
    if data_home is not None:
        overrides["data_root"] = data_home.expanduser().absolute()
        overrides["legacy_data_root"] = data_home.expanduser().absolute()
    if state_home is not None:
        overrides["state_root"] = state_home.expanduser().absolute()
    if cache_home is not None:
        overrides["cache_root"] = cache_home.expanduser().absolute()
    if session_home is not None:
        overrides["session_root"] = session_home.expanduser().absolute()
    if install_home is not None:
        overrides["install_root"] = install_home.expanduser().absolute()
    if codex_home is not None:
        overrides["codex_home"] = codex_home.expanduser().absolute()
    if bin_dir is not None:
        overrides["launcher_dir"] = bin_dir.expanduser().absolute()
    if overrides:
        resolved = replace(resolved, **overrides)
    return resolve_delivery_paths(
        resolved,
        product_version or read_product_version(),
        project_dir,
    )


LAUNCHER_MARKER = "# scientific-figure-builder launcher"


def launcher_text(
    runtime_python: PurePath,
    *,
    platform_name: str | None = None,
) -> str:
    """Render a stable launcher without embedding secrets or config values."""

    target_platform = os.name if platform_name is None else platform_name
    if target_platform == "nt":
        return (
            "@echo off\r\n"
            f'"{runtime_python}" -m figure_tools %*\r\n'
            f"{LAUNCHER_MARKER}\r\n"
        )
    return (
        "#!/bin/sh\n"
        f"{LAUNCHER_MARKER}\n"
        f"exec {shlex.quote(str(runtime_python))} -m figure_tools \"$@\"\n"
    )


def install_launcher(runtime_python: Path, launcher_file: Path | None) -> Path | None:
    """Install only our launcher; refuse to overwrite an unrelated file."""

    if launcher_file is None:
        return None
    launcher_file.parent.mkdir(parents=True, exist_ok=True)
    if launcher_file.exists():
        existing = launcher_file.read_text(encoding="utf-8", errors="replace")
        if LAUNCHER_MARKER not in existing:
            raise RuntimeError(f"refusing to overwrite unrelated launcher: {launcher_file}")
    temporary = launcher_file.with_name(f".{launcher_file.name}.tmp-{uuid.uuid4().hex[:8]}")
    temporary.write_text(launcher_text(runtime_python), encoding="utf-8")
    if os.name != "nt":
        os.chmod(temporary, 0o755)
    os.replace(temporary, launcher_file)
    return launcher_file


def validate_launcher_target(launcher_file: Path | None) -> None:
    if launcher_file is None or not launcher_file.exists():
        return
    existing = launcher_file.read_text(encoding="utf-8", errors="replace")
    if LAUNCHER_MARKER not in existing:
        raise RuntimeError(f"refusing to overwrite unrelated launcher: {launcher_file}")


def validate_source(source_dir: Path) -> None:
    missing = [
        item
        for item in (*RUNTIME_ITEMS, *SKILL_ITEMS, str(COMMAND_SOURCE))
        if not (source_dir / item).exists()
    ]
    if missing:
        raise RuntimeError(
            "Delivery package is incomplete; missing: " + ", ".join(sorted(set(missing)))
        )
    text = (source_dir / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n") or f"name: {SKILL_NAME}\n" not in text:
        raise RuntimeError("SKILL.md metadata is missing or has the wrong skill name")


def _copy_selected(source_dir: Path, destination: Path, items: Sequence[str]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in items:
        source = source_dir / item
        target = destination / item
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def runtime_python(runtime_dir: Path) -> Path:
    candidates = (
        runtime_dir / ".venv" / "bin" / "python",
        runtime_dir / ".venv" / "Scripts" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.absolute()
    raise RuntimeError("Dependency installation completed, but runtime Python was not found")


def sync_runtime(runtime_dir: Path, with_gui: bool = False) -> Path:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError(
            "`uv` is required. Install it first from https://docs.astral.sh/uv/."
        )
    command = [uv, "sync", "--frozen", "--no-dev", "--no-editable"]
    if with_gui:
        command.extend(("--extra", "gui"))
    command.extend(("--directory", str(runtime_dir)))
    subprocess.run(command, check=True)
    return runtime_python(runtime_dir)


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path.absolute()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def preflight_install(
    source_dir: Path,
    paths: DeliveryPaths,
    *,
    host_adapters: Sequence[HostDeliveryAdapter],
    with_gui: bool,
) -> None:
    """Validate every known failure mode before creating transaction state."""

    validate_source(source_dir)
    for adapter in host_adapters:
        adapter.preflight(paths)
    validate_launcher_target(paths.launcher_file)

    targets = [
        paths.runtime_dir,
        paths.state_dir,
        paths.staging_parent,
        paths.transaction_backup_parent,
        paths.install_lock_dir,
    ]
    if paths.launcher_file is not None:
        targets.append(paths.launcher_file)
    for adapter in host_adapters:
        targets.extend(adapter.targets(paths))
    for target in targets:
        parent = _nearest_existing_parent(target.parent)
        if not os.access(parent, os.W_OK):
            raise RuntimeError(f"installation target is not writable: {target.parent}")

    required_bytes = 2 * 1024**3 if with_gui else 256 * 1024**2
    free_bytes = shutil.disk_usage(_nearest_existing_parent(paths.runtime_dir.parent)).free
    if free_bytes < required_bytes:
        required_gib = required_bytes / 1024**3
        available_gib = free_bytes / 1024**3
        raise RuntimeError(
            f"insufficient disk space: {required_gib:.1f} GiB required, "
            f"{available_gib:.1f} GiB available"
        )


def _write_staged_text(path: Path, text: str, *, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable and os.name != "nt":
        os.chmod(path, 0o755)
    return path


def _gui_component_installed(runtime_python: Path, runtime_dir: Path) -> bool:
    result = subprocess.run(
        [
            str(runtime_python),
            "-c",
            (
                "import importlib.util; "
                "raise SystemExit(0 if importlib.util.find_spec('PySide6') else 1)"
            ),
        ],
        cwd=runtime_dir,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return result.returncode == 0


def smoke_test_mcp(runtime_python: Path, runtime_dir: Path) -> None:
    requests = "\n".join(
        (
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            "",
        )
    )
    result = subprocess.run(
        [str(runtime_python), "-m", "figure_tools.server"],
        input=requests,
        text=True,
        capture_output=True,
        cwd=runtime_dir,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"MCP self-check failed: {result.stderr.strip()}")
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 2:
        raise RuntimeError("MCP self-check returned an unexpected response")
    tools = lines[1].get("result", {}).get("tools", [])
    if len(tools) != 2:
        raise RuntimeError(f"MCP self-check expected 2 tools, found {len(tools)}")


def install(
    request: InstallRequest,
    *,
    runtime_sync: Callable[..., Path] = sync_runtime,
    run_smoke_test: bool = True,
    failure_injector: Callable[[str], None] | None = None,
) -> InstallResult:
    source_dir = request.source_dir.resolve()
    paths = request.paths
    adapters = host_delivery_adapters(request)
    with_gui = request.with_gui
    preflight_install(
        source_dir,
        paths,
        host_adapters=adapters,
        with_gui=with_gui,
    )
    previous_active = read_active_runtime(paths.active_runtime_file)
    previous_runtime = (
        Path(previous_active["runtime_dir"])
        if previous_active is not None
        and Path(previous_active["runtime_dir"]).is_dir()
        else None
    )

    def inject(stage: str) -> None:
        if failure_injector is not None:
            failure_injector(stage)

    active_runtime: dict[str, str] = {}
    transaction_id = ""
    committed_paths: list[str] = []
    with InstallTransaction(paths) as transaction:
        staged_runtime = transaction.stage_path("runtime")
        _copy_selected(source_dir, staged_runtime, RUNTIME_ITEMS)

        staged_runtime_python = runtime_sync(staged_runtime, with_gui)
        if run_smoke_test:
            smoke_test_mcp(staged_runtime_python, staged_runtime)
        runtime_python_relative = staged_runtime_python.relative_to(staged_runtime)
        final_runtime_python = paths.runtime_dir / runtime_python_relative
        staged_host_paths = tuple(
            staged
            for adapter in adapters
            for staged in adapter.stage(
                transaction, source_dir, paths, final_runtime_python
            )
        )

        staged_launcher = None
        if paths.launcher_file is not None:
            staged_launcher = _write_staged_text(
                transaction.stage_path("launcher"),
                launcher_text(final_runtime_python),
                executable=True,
            )

        active_runtime = active_runtime_metadata(paths)
        staged_active_runtime = _write_staged_text(
            transaction.stage_path("active-runtime.json"),
            json.dumps(active_runtime, indent=2) + "\n",
        )

        transaction.replace(staged_runtime, paths.runtime_dir)
        inject("runtime")
        staged_by_stage = {item.stage: item for item in staged_host_paths}
        for stage in ("opencode_skill", "codex_skill"):
            if item := staged_by_stage.get(stage):
                transaction.replace(item.staged, item.destination)
                inject(stage)
        if staged_launcher is not None and paths.launcher_file is not None:
            transaction.replace(staged_launcher, paths.launcher_file)
            inject("launcher")
        for stage in ("opencode_command", "opencode_config", "codex_config"):
            if item := staged_by_stage.get(stage):
                transaction.replace(item.staged, item.destination)
                inject(stage)
        transaction.replace(staged_active_runtime, paths.active_runtime_file)
        inject("active_runtime")
        transaction.commit()
        committed_paths = transaction.committed_paths
        transaction_id = transaction.transaction_id

    pruned_runtimes = prune_runtime_versions(paths, previous_runtime)
    runtime_python_path = runtime_python(paths.runtime_dir)
    launcher = paths.launcher_file if paths.launcher_file is not None else None
    launcher_warning = None
    if launcher is not None and launcher.is_file():
        path_entries = {
            Path(item).expanduser().resolve()
            for item in os.environ.get("PATH", "").split(os.pathsep)
            if item
        }
        if launcher.parent.resolve() not in path_entries:
            launcher_warning = f"Add {launcher.parent} to PATH to use `scientific-figure`."

    legacy_runtime = (
        paths.legacy_runtime_dir
        if paths.legacy_runtime_dir is not None and paths.legacy_runtime_dir.is_dir()
        else None
    )
    runtime_backup = (
        previous_runtime
        if previous_runtime is not None and previous_runtime != paths.runtime_dir
        else None
    )
    retained_paths = tuple(
        path for path in (legacy_runtime, runtime_backup) if path is not None
    )
    return InstallResult(
        skill=paths.skill_dir,
        command=paths.command_file,
        runtime=paths.runtime_dir,
        runtime_python=runtime_python_path,
        config=paths.config_file,
        runtime_backup=runtime_backup,
        codex_skill=paths.codex_skill_dir,
        codex_config=paths.codex_config_file,
        mcp_tools=2,
        gui_installed=_gui_component_installed(runtime_python_path, paths.runtime_dir),
        active_runtime=active_runtime,
        transaction_id=transaction_id,
        transaction_log=paths.transaction_log_dir / f"{transaction_id}.json",
        committed_paths=tuple(committed_paths),
        retained_paths=retained_paths,
        pruned_paths=tuple(Path(path) for path in pruned_runtimes),
        legacy_runtime_retained=legacy_runtime,
        launcher=launcher,
        launcher_warning=launcher_warning,
    )


def verify_delivery(
    paths: DeliveryPaths,
    *,
    verify_opencode: bool = True,
    verify_codex: bool = True,
    require_gui: bool = False,
) -> dict[str, object]:
    checks: dict[str, bool] = {
        "runtime": (paths.runtime_dir / "figure_tools" / "server.py").is_file(),
        "active_runtime": active_runtime_matches(paths),
    }
    if paths.launcher_file is not None:
        checks["launcher"] = (
            paths.launcher_file.is_file()
            and LAUNCHER_MARKER in paths.launcher_file.read_text(
                encoding="utf-8", errors="replace"
            )
        )
        checks["gui_resources"] = (
            (paths.runtime_dir / "figure_tools" / "resources" / "icon.svg").is_file()
            and (paths.runtime_dir / "figure_tools" / "resources" / "qml" / "Main.qml").is_file()
        )
    runtime_command: Path | None = None

    if verify_opencode:
        config = load_config(paths.config_file)
        mcp = config.get("mcp", {}).get(DEFAULT_MCP_NAME)
        opencode_checks = {
            "opencode_skill": (paths.skill_dir / "SKILL.md").is_file(),
            "opencode_command": paths.command_file.is_file(),
            "opencode_mcp_config": isinstance(mcp, dict),
        }
        checks.update(opencode_checks)
        command = mcp.get("command", []) if isinstance(mcp, dict) else []
        if command:
            runtime_command = Path(command[0])

    if verify_codex:
        codex_result = verify_codex_config(paths.codex_config_file, DEFAULT_MCP_NAME)
        codex_checks = {
            "codex_skill": (paths.codex_skill_dir / "SKILL.md").is_file(),
            "codex_mcp_config": codex_result["checks"]["mcp_table"],
        }
        checks.update(codex_checks)
        if runtime_command is None and codex_result["checks"]["command"]:
            import tomllib

            parsed = tomllib.loads(
                paths.codex_config_file.read_text(encoding="utf-8")
            )
            command = parsed["mcp_servers"][DEFAULT_MCP_NAME].get("command")
            if command:
                runtime_command = Path(command)

    if runtime_command is None:
        runtime_command = runtime_python(paths.runtime_dir)

    if runtime_command is not None and runtime_command.is_file():
        help_result = subprocess.run(
            [str(runtime_command), "-m", "figure_tools", "--help"],
            cwd=paths.runtime_dir, capture_output=True, text=True, timeout=15, check=False,
        )
        checks["cli_help"] = help_result.returncode == 0
        resource_result = subprocess.run(
            [str(runtime_command), "-c", "from importlib.resources import files; from figure_tools.resources_loader import read_gui_resource; read_gui_resource('icon.svg'); files('figure_tools.resources').joinpath('qml/Main.qml').read_text(encoding='utf-8')"],
            cwd=paths.runtime_dir, capture_output=True, text=True, timeout=15, check=False,
        )
        checks["gui_resource_import"] = resource_result.returncode == 0

    gui_installed = (
        _gui_component_installed(runtime_command, paths.runtime_dir)
        if runtime_command is not None and runtime_command.is_file()
        else False
    )
    if require_gui:
        checks["gui_component"] = gui_installed

    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise RuntimeError(f"Installation verification failed: {failed}")

    if runtime_command is not None and runtime_command.is_file():
        smoke_test_mcp(runtime_command, paths.runtime_dir)
    else:
        raise RuntimeError("Installation verification failed: MCP runtime is missing")

    return {
        "checks": checks,
        "mcp_tools": 2,
        "components": {"core": True, "gui": gui_installed},
    }


def build_parser() -> argparse.ArgumentParser:
    path_environment = default_path_environment()
    parser = argparse.ArgumentParser(
        description=(
            "Install and configure Scientific Figure Builder for OpenCode and Codex."
        )
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="Install the Skill for this project instead of globally.",
    )
    target_group = parser.add_mutually_exclusive_group()
    target_group.add_argument(
        "--codex",
        dest="target",
        action="store_const",
        const="runtime",
        help="Install the Core runtime for the Native Codex plugin.",
    )
    target_group.add_argument(
        "--opencode",
        dest="target",
        action="store_const",
        const="opencode",
        help="Install the Core runtime and OpenCode integration only.",
    )
    target_group.add_argument(
        "--all",
        dest="target",
        action="store_const",
        const="both",
        help="Explicitly install both legacy Agent integrations.",
    )
    target_group.add_argument(
        "--opencode-only",
        dest="target",
        action="store_const",
        const="opencode",
        help="Deprecated alias for --opencode.",
    )
    target_group.add_argument(
        "--codex-only",
        dest="target",
        action="store_const",
        const="codex-legacy",
        help="Deprecated legacy Codex Skill/config installation.",
    )
    target_group.add_argument(
        "--runtime-only",
        dest="target",
        action="store_const",
        const="runtime",
        help="Compatibility alias for the default Core runtime installation.",
    )
    parser.set_defaults(target="runtime")
    parser.add_argument(
        "--config-home",
        type=Path,
        default=path_environment.config_root,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--data-home",
        type=Path,
        default=path_environment.legacy_data_root,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--state-home",
        type=Path,
        default=path_environment.state_root,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--cache-home",
        type=Path,
        default=path_environment.cache_root,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--session-home",
        type=Path,
        default=path_environment.session_root,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--install-home",
        type=Path,
        default=path_environment.install_root,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--bin-dir",
        type=Path,
        default=path_environment.launcher_dir,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=path_environment.codex_home,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify an existing installation without changing it.",
    )
    parser.add_argument(
        "--with-gui",
        action="store_true",
        help="Install the optional Qt Configuration app; the default is Core only.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(raw_argv)
    compatibility_messages = {
        "--runtime-only": "--runtime-only is a compatibility alias; use ./install.sh or --codex.",
        "--opencode-only": "--opencode-only is deprecated; use --opencode.",
        "--codex-only": (
            "--codex-only installs the deprecated manual Codex integration; "
            "use --codex and install the Native plugin from the repo marketplace."
        ),
    }
    for option, message in compatibility_messages.items():
        if option in raw_argv:
            print(f"Compatibility notice: {message}", file=sys.stderr)
    install_opencode = args.target in {"both", "opencode"}
    install_codex = args.target in {"both", "codex-legacy"}
    product_version = read_product_version(args.source_dir)
    paths = delivery_paths(
        config_home=args.config_home.expanduser(),
        data_home=args.data_home.expanduser(),
        state_home=args.state_home.expanduser(),
        cache_home=args.cache_home.expanduser(),
        session_home=args.session_home.expanduser(),
        install_home=args.install_home.expanduser(),
        bin_dir=args.bin_dir.expanduser(),
        codex_home=args.codex_home.expanduser(),
        project_dir=args.project,
        product_version=product_version,
    )
    try:
        if args.verify:
            verification = verify_delivery(
                paths,
                verify_opencode=install_opencode,
                verify_codex=install_codex,
                require_gui=args.with_gui,
            )
            components = verification.get("components")
            gui_installed = (
                bool(components.get("gui")) if isinstance(components, dict) else False
            )
            print(
                f"Installation verified: {verification['mcp_tools']} MCP tools available."
            )
            print(
                "  Core runtime:    installed\n"
                f"  Configuration app: {'installed' if gui_installed else 'not installed'}"
            )
            return 0
        request = InstallRequest(
            source_dir=args.source_dir,
            paths=paths,
            target=args.target,
            scope="global" if paths.scope_id == "global" else "project",
            product_version=product_version,
            with_gui=args.with_gui,
        )
        result = install(request)
    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Installation interrupted; transaction rolled back.", file=sys.stderr)
        return 130

    print("Scientific Figure Builder installed successfully.")
    print(f"  Product version:   {paths.product_version}")
    print(f"  Transaction log:   {result.transaction_log}")
    print(f"  MCP:     {result.mcp_tools} tools verified")
    print("  Core runtime:      installed")
    if result.gui_installed:
        print("  Configuration app: installed")
    else:
        print("  Configuration app: not installed")
        print("  GUI install:       scientific-figure install-gui")
    if install_opencode:
        print(f"  OpenCode skill:   {result.skill}")
        print(f"  OpenCode command: /scientific-figure")
        print(f"  OpenCode config:  {result.config}")
    if install_codex:
        print(f"  Codex skill:      {result.codex_skill}")
        print(f"  Codex config:     {result.codex_config}")
    if result.launcher:
        print(f"  Launcher:         {result.launcher}")
    if result.launcher_warning:
        print(f"  PATH warning:     {result.launcher_warning}")
    if result.legacy_runtime_retained:
        print(
            "  Legacy runtime:    retained for rollback at "
            f"{result.legacy_runtime_retained}"
        )
    agents = []
    if install_opencode:
        agents.append("OpenCode")
    if install_codex:
        agents.append("Codex")
    if agents:
        print(f"Restart {'/'.join(agents)} and ask it to use `scientific-figure-builder`.")
    else:
        print("Core runtime ready for the Scientific Figure Builder Native plugin.")
    print(
        "Provider credentials use the system credential store when configured; "
        "environment-backed values were not written to disk."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
