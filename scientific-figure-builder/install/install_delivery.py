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
import tempfile
import time
import tomllib
import uuid
from dataclasses import replace
from pathlib import Path, PurePath
from typing import Callable, Sequence

for _parent in Path(__file__).resolve().parents:
    if (_parent / "figure_tools").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from figure_tools.install_paths import (  # noqa: E402
    DeliveryPaths,
    PathEnvironment,
    activate_runtime,
    active_runtime_matches,
    resolve_delivery_paths,
)

try:
    from .configure_opencode import (
        DEFAULT_MCP_NAME,
        apply_merge,
        load_config,
        mcp_entry_for_python,
    )
    from .configure_codex import (
        codex_mcp_entry,
        update_codex_mcp_config,
        verify_codex_config,
    )
except ImportError:  # Direct execution from install.sh.
    from configure_opencode import (
        DEFAULT_MCP_NAME,
        apply_merge,
        load_config,
        mcp_entry_for_python,
    )
    from configure_codex import (
        codex_mcp_entry,
        update_codex_mcp_config,
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


def _replace_directory(
    staged: Path,
    destination: Path,
    *,
    backup_root: Path | None = None,
) -> Path | None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if destination.exists():
        backup_parent = backup_root or destination.parent
        backup_parent.mkdir(parents=True, exist_ok=True)
        backup = backup_parent / (
            f"{destination.name}.backup-{time.strftime('%Y%m%d-%H%M%S')}-"
            f"{uuid.uuid4().hex[:8]}"
        )
        destination.replace(backup)
    staged.replace(destination)
    return backup


def _replace_file(source: Path, destination: Path) -> Path | None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if destination.exists() and destination.read_bytes() != source.read_bytes():
        backup = destination.with_suffix(
            destination.suffix
            + f".backup-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        )
        shutil.copy2(destination, backup)
    shutil.copy2(source, destination)
    return backup


def sync_runtime(runtime_dir: Path, with_gui: bool = False) -> Path:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError(
            "`uv` is required. Install it first from https://docs.astral.sh/uv/."
        )
    command = [uv, "sync", "--frozen", "--no-dev"]
    if with_gui:
        command.extend(("--extra", "gui"))
    command.extend(("--directory", str(runtime_dir)))
    subprocess.run(command, check=True)
    candidates = (
        runtime_dir / ".venv" / "bin" / "python",
        runtime_dir / ".venv" / "Scripts" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.absolute()
    raise RuntimeError("Dependency installation completed, but runtime Python was not found")


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


def install_delivery(
    source_dir: Path,
    paths: DeliveryPaths,
    *,
    runtime_sync: Callable[..., Path] = sync_runtime,
    run_smoke_test: bool = True,
    install_opencode: bool = True,
    install_codex: bool = True,
    with_gui: bool = False,
) -> dict[str, object]:
    source_dir = source_dir.resolve()
    validate_source(source_dir)

    # Parse before making any changes so an invalid existing config fails safely.
    if install_opencode:
        load_config(paths.config_file)
    if install_codex:
        codex_config_text = (
            paths.codex_config_file.read_text(encoding="utf-8")
            if paths.codex_config_file.exists()
            else ""
        )
        # Fail before changes if Codex config is not valid TOML.
        if codex_config_text.strip():
            import tomllib

            tomllib.loads(codex_config_text)
    validate_launcher_target(paths.launcher_file)

    paths.runtime_dir.parent.mkdir(parents=True, exist_ok=True)
    if install_opencode:
        paths.skill_dir.parent.mkdir(parents=True, exist_ok=True)
    if install_codex:
        paths.codex_skill_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{SKILL_NAME}-install-",
        dir=paths.runtime_dir.parent,
    ) as temp_root:
        temp_root_path = Path(temp_root)
        staged_runtime = temp_root_path / "runtime"
        staged_opencode_skill = temp_root_path / "skill-opencode"
        staged_codex_skill = temp_root_path / "skill-codex"
        _copy_selected(source_dir, staged_runtime, RUNTIME_ITEMS)
        if install_opencode:
            _copy_selected(source_dir, staged_opencode_skill, SKILL_ITEMS)
        if install_codex:
            _copy_selected(source_dir, staged_codex_skill, SKILL_ITEMS)

        runtime_backup = _replace_directory(staged_runtime, paths.runtime_dir)
        try:
            runtime_python = runtime_sync(paths.runtime_dir, with_gui)
            if run_smoke_test:
                smoke_test_mcp(runtime_python, paths.runtime_dir)
        except Exception:
            if paths.runtime_dir.exists():
                shutil.rmtree(paths.runtime_dir)
            if runtime_backup is not None:
                runtime_backup.replace(paths.runtime_dir)
            raise

        skill_backup = None
        if install_opencode:
            skill_backup = _replace_directory(
                staged_opencode_skill,
                paths.skill_dir,
                backup_root=paths.skill_dir.parent.parent / ".skill-backups",
            )

        codex_skill_backup = None
        if install_codex:
            codex_skill_backup = _replace_directory(
                staged_codex_skill,
                paths.codex_skill_dir,
                backup_root=paths.codex_skill_dir.parent.parent / ".skill-backups",
            )

    command_backup = None
    launcher = install_launcher(runtime_python, paths.launcher_file)
    launcher_warning = None
    if launcher is not None:
        path_entries = {
            Path(item).expanduser().resolve()
            for item in os.environ.get("PATH", "").split(os.pathsep)
            if item
        }
        if launcher.parent.resolve() not in path_entries:
            launcher_warning = f"Add {launcher.parent} to PATH to use `scientific-figure`."
    config_result = {"backup": None}
    if install_opencode:
        command_backup = _replace_file(source_dir / COMMAND_SOURCE, paths.command_file)
        mcp_entry = mcp_entry_for_python(runtime_python)
        config_result = apply_merge(
            paths.config_file,
            DEFAULT_MCP_NAME,
            mcp_entry,
            approver=lambda _diff: True,
            backup=True,
        )

    codex_config_result = {"backup": None}
    if install_codex:
        codex_config_result = update_codex_mcp_config(
            paths.codex_config_file,
            DEFAULT_MCP_NAME,
            codex_mcp_entry(runtime_python, paths.runtime_dir),
            backup=True,
        )

    active_runtime = activate_runtime(paths)

    return {
        "skill": str(paths.skill_dir),
        "command": str(paths.command_file),
        "runtime": str(paths.runtime_dir),
        "runtime_python": str(runtime_python),
        "config": str(paths.config_file),
        "config_backup": config_result["backup"],
        "runtime_backup": str(runtime_backup) if runtime_backup else None,
        "skill_backup": str(skill_backup) if skill_backup else None,
        "command_backup": str(command_backup) if command_backup else None,
        "codex_skill": str(paths.codex_skill_dir),
        "codex_skill_backup": str(codex_skill_backup) if codex_skill_backup else None,
        "codex_config": str(paths.codex_config_file),
        "codex_config_backup": codex_config_result["backup"],
        "mcp_tools": 2,
        "gui_installed": _gui_component_installed(runtime_python, paths.runtime_dir),
        "active_runtime": active_runtime,
        "legacy_runtime_retained": (
            str(paths.legacy_runtime_dir)
            if paths.legacy_runtime_dir is not None
            and paths.legacy_runtime_dir.is_dir()
            else None
        ),
        "launcher": str(launcher) if launcher else None,
        "launcher_warning": launcher_warning,
    }


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
            (paths.runtime_dir / "figure_tools" / "resources" / "gui.qss").is_file()
            and (paths.runtime_dir / "figure_tools" / "resources" / "icon.svg").is_file()
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

    if runtime_command is not None and runtime_command.is_file():
        help_result = subprocess.run(
            [str(runtime_command), "-m", "figure_tools", "--help"],
            cwd=paths.runtime_dir, capture_output=True, text=True, timeout=15, check=False,
        )
        checks["cli_help"] = help_result.returncode == 0
        resource_result = subprocess.run(
            [str(runtime_command), "-c", "from importlib.resources import files; from figure_tools.resources_loader import read_gui_resource; read_gui_resource('gui.qss'); read_gui_resource('icon.svg'); files('figure_tools.resources').joinpath('qml/Main.qml').read_text(encoding='utf-8')"],
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
        "--opencode-only",
        dest="target",
        action="store_const",
        const="opencode",
        help="Install only the OpenCode skill/command/MCP entry.",
    )
    target_group.add_argument(
        "--codex-only",
        dest="target",
        action="store_const",
        const="codex",
        help="Install only the Codex skill/MCP entry.",
    )
    target_group.add_argument(
        "--runtime-only",
        dest="target",
        action="store_const",
        const="runtime",
        help="Install only the Core runtime and global CLI for a Native plugin.",
    )
    parser.set_defaults(target="both")
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
    args = build_parser().parse_args(argv)
    install_opencode = args.target in {"both", "opencode"}
    install_codex = args.target in {"both", "codex"}
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
            result = verify_delivery(
                paths,
                verify_opencode=install_opencode,
                verify_codex=install_codex,
                require_gui=args.with_gui,
            )
            print(f"Installation verified: {result['mcp_tools']} MCP tools available.")
            print(
                "  Core runtime:    installed\n"
                f"  Configuration app: {'installed' if result['components']['gui'] else 'not installed'}"
            )
            return 0
        result = install_delivery(
            args.source_dir,
            paths,
            install_opencode=install_opencode,
            install_codex=install_codex,
            with_gui=args.with_gui,
        )
    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        return 1

    print("Scientific Figure Builder installed successfully.")
    print(f"  Product version:   {paths.product_version}")
    print(f"  MCP:     {result['mcp_tools']} tools verified")
    print("  Core runtime:      installed")
    if result["gui_installed"]:
        print("  Configuration app: installed")
    else:
        print("  Configuration app: not installed")
        print("  GUI install:       scientific-figure install-gui")
    if install_opencode:
        print(f"  OpenCode skill:   {result['skill']}")
        print(f"  OpenCode command: /scientific-figure")
        print(f"  OpenCode config:  {result['config']}")
    if install_codex:
        print(f"  Codex skill:      {result['codex_skill']}")
        print(f"  Codex config:     {result['codex_config']}")
    if result.get("launcher"):
        print(f"  Launcher:         {result['launcher']}")
    if result.get("launcher_warning"):
        print(f"  PATH warning:     {result['launcher_warning']}")
    if result.get("legacy_runtime_retained"):
        print(
            "  Legacy runtime:    retained for rollback at "
            f"{result['legacy_runtime_retained']}"
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
