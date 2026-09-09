"""Verified Product-bundle Local activation."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from figure_tools.codex_plugin import (
    MARKETPLACE_NAME,
    PLUGIN_NAME,
    PLUGIN_SELECTOR,
    find_codex_executable,
    native_plugin_configured,
)
from figure_tools.convergence import cleanup_local_versions
from figure_tools.install_paths import (
    PathEnvironment,
    activation_cache_dir,
    activate_runtime,
    native_plugin_marketplace_dir,
    read_active_runtime,
    resolve_delivery_paths,
)
from figure_tools.local_status import (
    LocalConclusion,
    LocalStatusRequest,
    PluginInstallation,
    RunningRuntimeInstance,
    collect_local_status,
    discover_running_runtime_instances,
)
from figure_tools.release_bundle import extract_product_bundle, verify_detached_checksum
from install.install_delivery import (
    InstallRequest,
    install,
    install_launcher,
    runtime_python,
    sync_runtime,
)


class PluginAdapter(Protocol):
    def install(self, product_root: Path, version: str) -> PluginInstallation: ...

    def restore(self, version: str | None) -> None: ...

    def finalize(self) -> None: ...


class HostTarget(str, Enum):
    RUNTIME = "runtime"
    CODEX = "codex"
    OPENCODE = "opencode"
    ALL = "all"

    @property
    def includes_codex(self) -> bool:
        return self in {HostTarget.CODEX, HostTarget.ALL}

    @property
    def includes_opencode(self) -> bool:
        return self in {HostTarget.OPENCODE, HostTarget.ALL}


class CodexPluginAdapter:
    """Install the bundled Native plugin through Codex's marketplace interface."""

    marketplace_name = MARKETPLACE_NAME
    plugin_selector = PLUGIN_SELECTOR

    def __init__(self, environment: PathEnvironment, *, codex: Path) -> None:
        self.environment = environment
        self.codex = codex
        self.marketplace = native_plugin_marketplace_dir(environment)
        self._backup: Path | None = None
        self._previous_source: str | None = None
        self._previous_version: str | None = None

    def install(self, product_root: Path, version: str) -> PluginInstallation:
        manifest_path = (
            product_root / "plugins" / "scientific-figure-builder"
            / ".codex-plugin" / "plugin.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("version") != version:
            raise RuntimeError("Native plugin version does not match Product bundle")

        marketplace = self._json(("plugin", "marketplace", "list", "--json"))
        for item in marketplace.get("marketplaces", []):
            if item.get("name") != self.marketplace_name:
                continue
            source = item.get("marketplaceSource") or {}
            if source.get("sourceType") == "local":
                self._previous_source = str(source.get("source"))
            break
        plugins = self._json((
            "plugin", "list", "--marketplace", self.marketplace_name, "--json",
        ))
        for item in plugins.get("installed", []):
            if item.get("name") == PLUGIN_NAME:
                self._previous_version = (
                    str(item["version"]) if item.get("version") is not None else None
                )
                break

        candidate = self.marketplace.with_name(
            f".{self.marketplace.name}.candidate-{uuid.uuid4().hex[:8]}"
        )
        candidate.mkdir(parents=True)
        shutil.copytree(product_root / ".agents", candidate / ".agents")
        shutil.copytree(product_root / "plugins", candidate / "plugins")
        if self.marketplace.exists():
            self._backup = self.marketplace.with_name(
                f".{self.marketplace.name}.backup-{uuid.uuid4().hex[:8]}"
            )
            os.replace(self.marketplace, self._backup)
        os.replace(candidate, self.marketplace)

        if self._previous_source is not None:
            self._json(("plugin", "marketplace", "remove", self.marketplace_name, "--json"))
        self._json(("plugin", "marketplace", "add", str(self.marketplace), "--json"))
        installed = self._json(("plugin", "add", self.plugin_selector, "--json"))
        installed_version = str(installed.get("version") or "")
        if installed_version != version:
            raise RuntimeError(
                f"Codex installed Native plugin {installed_version or 'unknown'}, "
                f"expected {version}"
            )
        return PluginInstallation(
            bool(installed.get("installed", True)),
            bool(installed.get("enabled", True)),
            installed_version,
        )

    def restore(self, version: str | None) -> None:
        if version is None:
            try:
                self._json(("plugin", "remove", self.plugin_selector, "--json"))
            except RuntimeError:
                pass
        try:
            self._json(("plugin", "marketplace", "remove", self.marketplace_name, "--json"))
        except RuntimeError:
            pass
        if self.marketplace.exists():
            shutil.rmtree(self.marketplace)
        if self._backup is not None and self._backup.exists():
            os.replace(self._backup, self.marketplace)
        if self._previous_source is not None:
            self._json(("plugin", "marketplace", "add", self._previous_source, "--json"))
        if version is not None:
            self._json(("plugin", "add", self.plugin_selector, "--json"))

    def finalize(self) -> None:
        if self._backup is not None and self._backup.exists():
            shutil.rmtree(self._backup)
        self._backup = None

    def _json(self, arguments: tuple[str, ...]) -> dict[str, Any]:
        completed = subprocess.run(
            [str(self.codex), *arguments],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Codex plugin command failed: {detail}")
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("Codex plugin command returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Codex plugin command returned an invalid result")
        return payload


@dataclass(frozen=True)
class ActivationRequest:
    bundle: Path
    environment: PathEnvironment
    expected_version: str | None = None
    host: HostTarget | str = HostTarget.CODEX
    with_gui: bool = False

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "host", HostTarget(self.host))
        except ValueError as exc:
            raise ValueError(f"unsupported activation host: {self.host}") from exc


@dataclass(frozen=True)
class ActivationResult:
    product_version: str
    active_runtime: Path
    plugin: PluginInstallation
    conclusion: LocalConclusion
    stale_instances: tuple[int, ...]
    retained_runtimes: tuple[Path, ...]
    transaction_log: Path

    @property
    def exit_code(self) -> int:
        return self.conclusion.exit_code

    def to_dict(self) -> dict[str, object]:
        return {
            "product_version": self.product_version,
            "active_runtime": str(self.active_runtime),
            "plugin": asdict(self.plugin),
            "conclusion": self.conclusion,
            "exit_code": self.exit_code,
            "stale_instances": list(self.stale_instances),
            "retained_runtimes": [str(path) for path in self.retained_runtimes],
            "transaction_log": str(self.transaction_log),
        }


@dataclass(frozen=True)
class SavedPath:
    original: Path
    backup: Path
    existed: bool


def activate_local(
    request: ActivationRequest,
    *,
    plugin_adapter: PluginAdapter | None = None,
    runtime_sync: Callable[[Path, bool], Path] = sync_runtime,
    running_instances: Iterable[RunningRuntimeInstance] | None = None,
) -> ActivationResult:
    """Install one verified bundle and report local version convergence."""

    target = HostTarget(request.host)
    supplied_instances = tuple(running_instances) if running_instances is not None else None
    selected_plugin_adapter = plugin_adapter
    if selected_plugin_adapter is None:
        selected_plugin_adapter = (
            CodexPluginAdapter(request.environment, codex=find_codex_executable())
            if target.includes_codex
            else NoPluginAdapter()
        )
    cache_root = activation_cache_dir(request.environment)
    cache_root.mkdir(parents=True, exist_ok=True)
    verify_detached_checksum(request.bundle)
    with tempfile.TemporaryDirectory(dir=cache_root, prefix="activation-") as temporary:
        extraction = Path(temporary) / "product"
        manifest, product_root = extract_product_bundle(
            request.bundle,
            extraction,
            expected_version=request.expected_version,
        )
        source_dir = product_root / "scientific-figure-builder"
        paths = resolve_delivery_paths(
            request.environment, manifest.product_version,
        )
        host_snapshot = (
            _save_paths(
                (paths.skill_dir, paths.command_file, paths.config_file),
                Path(temporary) / "host-backup",
            )
            if target.includes_opencode
            else ()
        )
        previous_active = read_active_runtime(paths.active_runtime_file)
        delivery_target = (
            "opencode" if target.includes_opencode else "runtime"
        )
        installed = install(
            InstallRequest(
                source_dir=source_dir,
                paths=paths,
                target=delivery_target,
                scope="global",
                product_version=manifest.product_version,
                with_gui=request.with_gui,
                defer_runtime_pruning=True,
            ),
            runtime_sync=runtime_sync,
        )
        try:
            plugin = (
                selected_plugin_adapter.install(product_root, manifest.product_version)
                if target.includes_codex
                else PluginInstallation(False, False, None)
            )
            selected_instances = (
                discover_running_runtime_instances(request.environment)
                if supplied_instances is None else supplied_instances
            )
            status = collect_local_status(
                LocalStatusRequest(
                    environment=request.environment,
                    cli_version=manifest.product_version,
                ),
                plugin=(
                    plugin if target.includes_codex
                    else PluginInstallation(True, True, manifest.product_version)
                ),
                running_instances=selected_instances,
            )
            if status.conclusion not in {
                LocalConclusion.CONVERGED,
                LocalConclusion.RESTART_REQUIRED,
            }:
                raise RuntimeError(
                    f"Local activation did not converge: {status.conclusion}"
                )
            selected_plugin_adapter.finalize()
        except Exception:  # noqa: BLE001 - preserve boundary error after compensation
            _restore_previous_installation(
                request,
                paths.runtime_dir,
                previous_active,
                selected_plugin_adapter,
            )
            _restore_paths(host_snapshot)
            raise
        cleanup_local_versions(
            request.environment,
            running_instances=selected_instances,
        )
        status = collect_local_status(
            LocalStatusRequest(
                environment=request.environment,
                cli_version=manifest.product_version,
            ),
            plugin=plugin if target.includes_codex else PluginInstallation(
                True, True, manifest.product_version,
            ),
            running_instances=selected_instances,
        )
        return ActivationResult(
            product_version=manifest.product_version,
            active_runtime=paths.runtime_dir,
            plugin=plugin,
            conclusion=status.conclusion,
            stale_instances=status.stale_instances,
            retained_runtimes=status.retained_runtimes,
            transaction_log=installed.transaction_log,
        )


def _restore_previous_installation(
    request: ActivationRequest,
    failed_runtime: Path,
    previous_active: dict[str, str] | None,
    plugin_adapter: PluginAdapter,
) -> None:
    previous_version = previous_active.get("version") if previous_active else None
    plugin_adapter.restore(previous_version)
    if previous_version is not None:
        previous = resolve_delivery_paths(request.environment, previous_version)
        if previous.runtime_dir.is_dir():
            activate_runtime(previous)
            install_launcher(runtime_python(previous.runtime_dir), previous.launcher_file)
    if failed_runtime.is_dir():
        shutil.rmtree(failed_runtime)


def _save_paths(paths: tuple[Path, ...], backup_root: Path) -> tuple[SavedPath, ...]:
    saved: list[SavedPath] = []
    for index, original in enumerate(paths):
        backup = backup_root / str(index)
        existed = original.exists()
        if existed:
            backup.parent.mkdir(parents=True, exist_ok=True)
            if original.is_dir():
                shutil.copytree(original, backup)
            else:
                shutil.copy2(original, backup)
        saved.append(SavedPath(original=original, backup=backup, existed=existed))
    return tuple(saved)


def _restore_paths(saved: tuple[SavedPath, ...]) -> None:
    for item in saved:
        if item.original.is_dir():
            shutil.rmtree(item.original)
        elif item.original.exists():
            item.original.unlink()
        if not item.existed:
            continue
        item.original.parent.mkdir(parents=True, exist_ok=True)
        if item.backup.is_dir():
            shutil.copytree(item.backup, item.original)
        else:
            shutil.copy2(item.backup, item.original)


class NoPluginAdapter:
    def install(self, product_root: Path, version: str) -> PluginInstallation:
        del product_root
        return PluginInstallation(True, True, version)

    def restore(self, version: str | None) -> None:
        del version
        return None

    def finalize(self) -> None:
        return None


def detect_installed_host(environment: PathEnvironment) -> HostTarget:
    """Preserve the currently installed host set for an update."""

    codex = native_plugin_configured(environment)
    opencode_skill = (
        environment.config_root / "opencode" / "skills"
        / "scientific-figure-builder" / "SKILL.md"
    )
    opencode = opencode_skill.is_file()
    if codex and opencode:
        return HostTarget.ALL
    if opencode:
        return HostTarget.OPENCODE
    if codex:
        return HostTarget.CODEX
    return HostTarget.RUNTIME


def preserve_gui_selection() -> bool:
    """Keep GUI installation shape unless the caller explicitly changes it."""

    return importlib.util.find_spec("PySide6") is not None


__all__ = [
    "ActivationRequest",
    "ActivationResult",
    "CodexPluginAdapter",
    "HostTarget",
    "detect_installed_host",
    "preserve_gui_selection",
    "PluginAdapter",
    "activate_local",
]
