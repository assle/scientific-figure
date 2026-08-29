"""Optional component discovery and installation for the Core runtime."""

from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

from figure_tools.install_paths import discover_runtime_directory


GUI_INSTALL_COMMAND = "scientific-figure install-gui"


def gui_available() -> bool:
    """Return whether the optional Qt runtime is available without importing it."""

    return importlib.util.find_spec("PySide6") is not None


def runtime_directory() -> Path:
    """Locate the installed source runtime that owns ``pyproject.toml``."""

    return discover_runtime_directory(
        executable=Path(sys.executable),
        module_file=Path(__file__),
    )


def install_gui_component(runtime_dir: Path | None = None) -> Path:
    """Transactionally install or upgrade the GUI extra for the Global runtime."""

    root = (runtime_dir or runtime_directory()).absolute()
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError(
            "`uv` is required to install the GUI component; install it from "
            "https://docs.astral.sh/uv/ and retry"
        )
    installer = root / "install" / "install_delivery.py"
    if not installer.is_file():
        raise RuntimeError(f"installed Core runtime has no installer: {installer}")
    install_environment = dict(os.environ)
    install_environment.setdefault(
        "SCIENTIFIC_FIGURE_INSTALL_HOME",
        str(root.parents[2]),
    )
    subprocess.run(
        [
            uv,
            "run",
            "--directory",
            str(root),
            "python",
            "-m",
            "install.install_delivery",
            "--source-dir",
            str(root),
            "--codex",
            "--with-gui",
        ],
        check=True,
        env=install_environment,
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
