"""Optional component discovery and installation for the Core runtime."""

from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


GUI_INSTALL_COMMAND = "scientific-figure install-gui"


def gui_available() -> bool:
    """Return whether the optional Qt runtime is available without importing it."""

    return importlib.util.find_spec("PySide6") is not None


def runtime_directory() -> Path:
    """Locate the installed source runtime that owns ``pyproject.toml``."""

    explicit = os.environ.get("SCIENTIFIC_FIGURE_RUNTIME_DIR")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())

    executable = Path(sys.executable).absolute()
    if (
        executable.parent.name.lower() in {"bin", "scripts"}
        and executable.parent.parent.name == ".venv"
    ):
        candidates.append(executable.parent.parent.parent)
    candidates.append(Path(__file__).resolve().parents[1])

    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file() and (candidate / "uv.lock").is_file():
            return candidate.absolute()
    raise RuntimeError(
        "could not locate the Scientific Figure Builder Core runtime; "
        "rerun the source installer with `--with-gui`"
    )


def install_gui_component(runtime_dir: Path | None = None) -> Path:
    """Install or upgrade the GUI extra in the current private runtime."""

    root = (runtime_dir or runtime_directory()).absolute()
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError(
            "`uv` is required to install the GUI component; install it from "
            "https://docs.astral.sh/uv/ and retry"
        )
    subprocess.run(
        [
            uv,
            "sync",
            "--frozen",
            "--no-dev",
            "--extra",
            "gui",
            "--directory",
            str(root),
        ],
        check=True,
    )
    importlib.invalidate_caches()
    if not gui_available():
        raise RuntimeError("GUI dependency installation completed, but PySide6 is unavailable")
    return root


__all__ = [
    "GUI_INSTALL_COMMAND",
    "gui_available",
    "install_gui_component",
    "runtime_directory",
]
