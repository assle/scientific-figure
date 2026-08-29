"""Canonical filesystem layout for install, runtime, verify, and uninstall."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


APP_NAME = "scientific-figure-builder"
WINDOWS_APP_DIR = "ScientificFigureBuilder"


def _absolute_path(value: str | os.PathLike[str], *, name: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path: {value}")
    return path


def _override(
    environ: Mapping[str, str], name: str, default: Path,
) -> Path:
    value = environ.get(name)
    return _absolute_path(value, name=name) if value else default


@dataclass(frozen=True)
class PathEnvironment:
    """Resolved user-level path categories and installation prefix."""

    home: Path
    config_root: Path
    data_root: Path
    state_root: Path
    cache_root: Path
    session_root: Path
    install_root: Path
    launcher_dir: Path
    codex_home: Path
    legacy_data_root: Path
    platform_name: str

    @classmethod
    def from_environ(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        home: Path | None = None,
        platform_name: str | None = None,
    ) -> "PathEnvironment":
        env = os.environ if environ is None else environ
        resolved_home = (home or Path.home()).expanduser().absolute()
        platform = platform_name or os.name

        if platform == "nt":
            local = _override(
                env,
                "LOCALAPPDATA",
                resolved_home / "AppData" / "Local",
            )
            roaming = _override(
                env,
                "APPDATA",
                resolved_home / "AppData" / "Roaming",
            )
            config_default = roaming
            data_default = local
            state_default = local / "State"
            cache_default = local / "Cache"
            session_default = _override(env, "TEMP", local / "Temp")
            install_default = local / "Programs" / WINDOWS_APP_DIR
        else:
            config_default = resolved_home / ".config"
            data_default = resolved_home / ".local" / "share"
            state_default = resolved_home / ".local" / "state"
            cache_default = resolved_home / ".cache"
            session_default = Path(tempfile.gettempdir())
            install_default = resolved_home / ".local" / "lib" / APP_NAME

        config_root = _override(env, "XDG_CONFIG_HOME", config_default)
        data_root = _override(env, "XDG_DATA_HOME", data_default)
        state_root = _override(env, "XDG_STATE_HOME", state_default)
        cache_root = _override(env, "XDG_CACHE_HOME", cache_default)
        session_root = _override(env, "XDG_RUNTIME_DIR", session_default)
        install_root = _override(
            env,
            "SCIENTIFIC_FIGURE_INSTALL_HOME",
            install_default,
        )
        launcher_default = (
            install_root / "bin"
            if platform == "nt"
            else resolved_home / ".local" / "bin"
        )
        launcher_dir = _override(
            env,
            "SCIENTIFIC_FIGURE_BIN_DIR",
            launcher_default,
        )
        codex_home = _override(
            env,
            "CODEX_HOME",
            resolved_home / ".codex",
        )
        # The previous installer used this path on every platform.
        legacy_data_root = _override(
            env,
            "XDG_DATA_HOME",
            resolved_home / ".local" / "share",
        )
        return cls(
            home=resolved_home,
            config_root=config_root,
            data_root=data_root,
            state_root=state_root,
            cache_root=cache_root,
            session_root=session_root,
            install_root=install_root,
            launcher_dir=launcher_dir,
            codex_home=codex_home,
            legacy_data_root=legacy_data_root,
            platform_name=platform,
        )


@dataclass(frozen=True)
class DeliveryPaths:
    product_version: str
    scope_id: str
    runtime_scope_dir: Path
    runtime_dir: Path
    active_runtime_file: Path
    legacy_runtime_dir: Path | None
    state_dir: Path
    cache_dir: Path
    session_dir: Path
    skill_dir: Path
    command_file: Path
    config_file: Path
    codex_skill_dir: Path
    codex_config_file: Path
    launcher_file: Path | None


def _project_scope_id(project_dir: Path) -> str:
    digest = hashlib.sha256(str(project_dir.resolve()).encode("utf-8")).hexdigest()
    return digest[:16]


def resolve_delivery_paths(
    environment: PathEnvironment,
    product_version: str,
    project_dir: Path | None = None,
) -> DeliveryPaths:
    """Resolve every product path for one global or project installation."""

    if project_dir is None:
        scope_id = "global"
        scope_dir = environment.install_root / "global"
        scope_state = environment.state_root / APP_NAME / "global"
        scope_cache = environment.cache_root / APP_NAME / "global"
        scope_session = environment.session_root / APP_NAME / "global"
        opencode_home = environment.config_root / "opencode"
        codex_home = environment.codex_home
        json_file = opencode_home / "opencode.json"
        jsonc_file = json_file.with_suffix(".jsonc")
        config_file = (
            jsonc_file if jsonc_file.exists() and not json_file.exists() else json_file
        )
        launcher_file = environment.launcher_dir / (
            "scientific-figure.cmd"
            if environment.platform_name == "nt"
            else "scientific-figure"
        )
        legacy_runtime_dir: Path | None = environment.legacy_data_root / APP_NAME
    else:
        project = project_dir.expanduser().resolve()
        scope_id = _project_scope_id(project)
        scope_dir = environment.install_root / "projects" / scope_id
        scope_state = environment.state_root / APP_NAME / "projects" / scope_id
        scope_cache = environment.cache_root / APP_NAME / "projects" / scope_id
        scope_session = environment.session_root / APP_NAME / "projects" / scope_id
        opencode_home = project / ".opencode"
        codex_home = project / ".codex"
        candidates = (
            project / "opencode.json",
            project / "opencode.jsonc",
            opencode_home / "opencode.json",
            opencode_home / "opencode.jsonc",
        )
        config_file = next((path for path in candidates if path.exists()), candidates[0])
        launcher_file = None
        legacy_runtime_dir = None

    runtime_dir = scope_dir / "runtimes" / product_version
    return DeliveryPaths(
        product_version=product_version,
        scope_id=scope_id,
        runtime_scope_dir=scope_dir,
        runtime_dir=runtime_dir,
        active_runtime_file=scope_dir / "active-runtime.json",
        legacy_runtime_dir=legacy_runtime_dir,
        state_dir=scope_state,
        cache_dir=scope_cache,
        session_dir=scope_session,
        skill_dir=opencode_home / "skills" / APP_NAME,
        command_file=opencode_home / "commands" / "scientific-figure.md",
        config_file=config_file,
        codex_skill_dir=codex_home / "skills" / APP_NAME,
        codex_config_file=codex_home / "config.toml",
        launcher_file=launcher_file,
    )


def read_active_runtime(path: Path) -> dict[str, str] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("runtime_dir"), str):
        raise ValueError(f"invalid active runtime metadata: {path}")
    return {str(key): str(value) for key, value in data.items()}


def activate_runtime(paths: DeliveryPaths) -> dict[str, str]:
    """Atomically record the verified runtime selected for this install scope."""

    paths.active_runtime_file.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": paths.product_version,
        "runtime_dir": str(paths.runtime_dir.absolute()),
        "scope": paths.scope_id,
    }
    if paths.legacy_runtime_dir is not None and paths.legacy_runtime_dir.is_dir():
        data["migrated_from"] = str(paths.legacy_runtime_dir.absolute())
    temporary = paths.active_runtime_file.with_name(
        f".{paths.active_runtime_file.name}.tmp-{uuid.uuid4().hex[:8]}"
    )
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, paths.active_runtime_file)
    return data


def active_runtime_matches(paths: DeliveryPaths) -> bool:
    active = read_active_runtime(paths.active_runtime_file)
    return bool(
        active
        and active.get("version") == paths.product_version
        and Path(active["runtime_dir"]) == paths.runtime_dir.absolute()
    )


def discover_runtime_directory(
    *,
    executable: Path,
    module_file: Path,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Find the active runtime for runtime-owned maintenance commands."""

    env = os.environ if environ is None else environ
    explicit = env.get("SCIENTIFIC_FIGURE_RUNTIME_DIR")
    candidates: list[Path] = []
    if explicit:
        candidates.append(_absolute_path(explicit, name="SCIENTIFIC_FIGURE_RUNTIME_DIR"))

    absolute_executable = executable.absolute()
    if (
        absolute_executable.parent.name.lower() in {"bin", "scripts"}
        and absolute_executable.parent.parent.name == ".venv"
    ):
        candidates.append(absolute_executable.parent.parent.parent)
    candidates.append(module_file.resolve().parents[1])

    try:
        environment = PathEnvironment.from_environ(env)
        active = read_active_runtime(
            environment.install_root / "global" / "active-runtime.json"
        )
        if active:
            candidates.append(Path(active["runtime_dir"]))
    except (OSError, ValueError, json.JSONDecodeError):
        pass

    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file() and (candidate / "uv.lock").is_file():
            return candidate.absolute()
    raise RuntimeError(
        "could not locate the Scientific Figure Builder Core runtime; "
        "rerun the source installer with `--with-gui`"
    )


__all__ = [
    "APP_NAME",
    "DeliveryPaths",
    "PathEnvironment",
    "activate_runtime",
    "active_runtime_matches",
    "discover_runtime_directory",
    "read_active_runtime",
    "resolve_delivery_paths",
]
