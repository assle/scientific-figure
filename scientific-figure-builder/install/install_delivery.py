"""One-command installer for the Scientific Figure Builder delivery package.

The installer keeps secrets out of files. It installs a private runtime,
publishes the Skill and slash command to OpenCode's discovery directories,
installs the Skill for Codex, merges MCP entries into both configuration files
without replacing unrelated configuration, and verifies the installed MCP
server before reporting success.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

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
    "install/configure_opencode.py",
    "install/configure_codex.py",
    "install.sh",
    "SKILL.md",
    "pyproject.toml",
    "uv.lock",
    "LICENSE",
)
SKILL_ITEMS = ("SKILL.md", "references", "schemas", "templates")
COMMAND_SOURCE = Path("commands") / "scientific-figure.md"


@dataclass(frozen=True)
class DeliveryPaths:
    runtime_dir: Path
    skill_dir: Path
    command_file: Path
    config_file: Path
    codex_skill_dir: Path
    codex_config_file: Path


def default_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def default_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def delivery_paths(
    *,
    config_home: Path,
    data_home: Path,
    project_dir: Path | None = None,
    codex_home: Path | None = None,
) -> DeliveryPaths:
    if project_dir is None:
        opencode_home = config_home / "opencode"
        codex_home = codex_home or default_codex_home()
        json_file = opencode_home / "opencode.json"
        jsonc_file = json_file.with_suffix(".jsonc")
        config_file = (
            jsonc_file if jsonc_file.exists() and not json_file.exists() else json_file
        )
        codex_config_file = codex_home / "config.toml"
    else:
        project_dir = project_dir.resolve()
        opencode_home = project_dir / ".opencode"
        codex_home = codex_home or (project_dir / ".codex")
        candidates = (
            project_dir / "opencode.json",
            project_dir / "opencode.jsonc",
            opencode_home / "opencode.json",
            opencode_home / "opencode.jsonc",
        )
        config_file = next((path for path in candidates if path.exists()), candidates[0])
        codex_config_file = codex_home / "config.toml"
    return DeliveryPaths(
        runtime_dir=data_home / SKILL_NAME,
        skill_dir=opencode_home / "skills" / SKILL_NAME,
        command_file=opencode_home / "commands" / "scientific-figure.md",
        config_file=config_file,
        codex_skill_dir=codex_home / "skills" / SKILL_NAME,
        codex_config_file=codex_config_file,
    )


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


def sync_runtime(runtime_dir: Path, *, with_ark: bool = True) -> Path:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError(
            "`uv` is required. Install it first from https://docs.astral.sh/uv/."
        )
    command = [uv, "sync", "--frozen", "--no-dev", "--directory", str(runtime_dir)]
    if with_ark:
        command.extend(["--extra", "ark"])
    subprocess.run(command, check=True)
    candidates = (
        runtime_dir / ".venv" / "bin" / "python",
        runtime_dir / ".venv" / "Scripts" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.absolute()
    raise RuntimeError("Dependency installation completed, but runtime Python was not found")


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
    if len(tools) != 15:
        raise RuntimeError(f"MCP self-check expected 15 tools, found {len(tools)}")


def install_delivery(
    source_dir: Path,
    paths: DeliveryPaths,
    *,
    with_ark: bool = True,
    runtime_sync: Callable[..., Path] = sync_runtime,
    run_smoke_test: bool = True,
    install_opencode: bool = True,
    install_codex: bool = True,
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
            runtime_python = runtime_sync(paths.runtime_dir, with_ark=with_ark)
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
        "mcp_tools": 15,
    }


def verify_delivery(
    paths: DeliveryPaths,
    *,
    verify_opencode: bool = True,
    verify_codex: bool = True,
) -> dict[str, object]:
    checks: dict[str, bool] = {
        "runtime": (paths.runtime_dir / "figure_tools" / "server.py").is_file(),
    }
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

    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise RuntimeError(f"Installation verification failed: {failed}")

    if runtime_command is not None and runtime_command.is_file():
        smoke_test_mcp(runtime_command, paths.runtime_dir)
    else:
        raise RuntimeError("Installation verification failed: MCP runtime is missing")

    return {"checks": checks, "mcp_tools": 15}


def build_parser() -> argparse.ArgumentParser:
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
    parser.set_defaults(target="both")
    parser.add_argument(
        "--config-home",
        type=Path,
        default=default_config_home(),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--data-home",
        type=Path,
        default=default_data_home(),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--without-ark",
        action="store_true",
        help="Skip the optional Volcengine Ark SDK and install local plotting only.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify an existing installation without changing it.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    install_opencode = args.target in {"both", "opencode"}
    install_codex = args.target in {"both", "codex"}
    paths = delivery_paths(
        config_home=args.config_home.expanduser(),
        data_home=args.data_home.expanduser(),
        project_dir=args.project,
    )
    try:
        if args.verify:
            result = verify_delivery(
                paths,
                verify_opencode=install_opencode,
                verify_codex=install_codex,
            )
            print(f"Installation verified: {result['mcp_tools']} MCP tools available.")
            return 0
        result = install_delivery(
            args.source_dir,
            paths,
            with_ark=not args.without_ark,
            install_opencode=install_opencode,
            install_codex=install_codex,
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
    print(f"  MCP:     {result['mcp_tools']} tools verified")
    if install_opencode:
        print(f"  OpenCode skill:   {result['skill']}")
        print(f"  OpenCode command: /scientific-figure")
        print(f"  OpenCode config:  {result['config']}")
    if install_codex:
        print(f"  Codex skill:      {result['codex_skill']}")
        print(f"  Codex config:     {result['codex_config']}")
    agents = []
    if install_opencode:
        agents.append("OpenCode")
    if install_codex:
        agents.append("Codex")
    print(f"Restart {'/'.join(agents)} and ask it to use `scientific-figure-builder`.")
    print("Provider credentials stay in environment variables and were not written to disk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
