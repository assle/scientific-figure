"""Project initializer CLI tests (plan section 14)."""

from __future__ import annotations

import json
from pathlib import Path

from figure_tools import __version__
from figure_tools.__main__ import main


def test_cli_init_creates_project_config(tmp_path: Path, capsys):
    rc = main(["init", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / ".scientific-figure" / "project.yaml").is_file()
    out = capsys.readouterr().out
    cfg = json.loads(out)
    assert set(cfg["models"]) == {
        "image_generate", "vision_analyze", "vision_validate",
    }


def test_cli_init_defaults_to_cwd(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = main(["init"])
    assert rc == 0
    assert (tmp_path / ".scientific-figure" / "style_bible.json").is_file()


def test_cli_no_args_prints_usage(capsys):
    rc = main([])
    assert rc == 2


def test_cli_reports_installed_product_version(capsys):
    rc = main(["--version"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == f"scientific-figure {__version__}"


def test_cli_installs_optional_gui_component(tmp_path: Path, monkeypatch, capsys):
    import figure_tools.components as components

    monkeypatch.setattr(components, "install_gui_component", lambda: tmp_path)
    assert main(["install-gui"]) == 0
    assert f"installed successfully in {tmp_path}" in capsys.readouterr().out


def test_cli_gui_missing_dependency_has_actionable_error(monkeypatch, capsys):
    import figure_tools.gui as gui

    monkeypatch.setattr(gui, "QApplication", None)
    assert main(["gui"]) == 1
    captured = capsys.readouterr()
    assert "scientific-figure install-gui" in captured.err
    assert "Traceback" not in captured.err
