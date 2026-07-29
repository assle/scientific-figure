"""Project initializer CLI tests (plan section 14)."""

from __future__ import annotations

import json
from pathlib import Path

from figure_tools.__main__ import main


def test_cli_init_creates_project_config(tmp_path: Path, capsys):
    rc = main(["init", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / ".scientific-figure" / "project.yaml").is_file()
    out = capsys.readouterr().out
    cfg = json.loads(out)
    for role in ("image_generate", "image_edit", "vision_analyze", "vision_validate"):
        assert role in cfg["models"]


def test_cli_init_defaults_to_cwd(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = main(["init"])
    assert rc == 0
    assert (tmp_path / ".scientific-figure" / "style_bible.json").is_file()


def test_cli_no_args_prints_usage(capsys):
    rc = main([])
    assert rc == 2
