"""Optional component boundaries for the Core runtime."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

from figure_tools import components


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def test_gui_is_an_optional_dependency_only() -> None:
    project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    core = [str(item).lower() for item in project["project"]["dependencies"]]
    gui = [
        str(item).lower()
        for item in project["project"]["optional-dependencies"]["gui"]
    ]
    assert not any(item.startswith("pyside6") for item in core)
    assert any(item.startswith("pyside6") for item in gui)


def test_core_import_graph_does_not_import_qt() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import figure_tools; import figure_tools.server; "
                "print(any(name.startswith('PySide6') for name in sys.modules))"
            ),
        ],
        cwd=PACKAGE_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_runtime_directory_honors_explicit_installed_runtime(
    tmp_path: Path, monkeypatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    monkeypatch.setenv("SCIENTIFIC_FIGURE_RUNTIME_DIR", str(tmp_path))
    assert components.runtime_directory() == tmp_path.absolute()


def test_install_gui_component_syncs_the_gui_extra(tmp_path: Path, monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []
    installer = tmp_path / "install" / "install_delivery.py"
    installer.parent.mkdir()
    installer.write_text("", encoding="utf-8")
    monkeypatch.setattr(components.shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(
        components.subprocess,
        "run",
        lambda command, check, env: calls.append((command, env)),
    )
    monkeypatch.setattr(components, "gui_available", lambda: True)

    assert components.install_gui_component(tmp_path) == tmp_path.absolute()
    assert calls[0][0] == [
        "/usr/bin/uv",
        "run",
        "--directory",
        str(tmp_path.absolute()),
        "python",
        "-m",
        "install.install_delivery",
        "--source-dir",
        str(tmp_path.absolute()),
        "--codex",
        "--with-gui",
    ]
    assert calls[0][1]["SCIENTIFIC_FIGURE_INSTALL_HOME"] == str(
        tmp_path.absolute().parents[2]
    )
