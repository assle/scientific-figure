"""Canonical Native Codex plugin identity and host discovery."""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from typing import Mapping

from figure_tools.install_paths import PathEnvironment


PLUGIN_NAME = "scientific-figure-builder"
MARKETPLACE_NAME = "scientific-figure"
PLUGIN_SELECTOR = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"


def find_codex_executable(environ: Mapping[str, str] | None = None) -> Path:
    path = environ.get("PATH") if environ is not None else None
    located = shutil.which("codex", path=path)
    if located:
        return Path(located)
    macos = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    if macos.is_file():
        return macos
    raise RuntimeError("Codex CLI is required to manage the Native plugin")


def native_plugin_configured(environment: PathEnvironment) -> bool:
    config = environment.codex_home / "config.toml"
    if not config.is_file():
        return False
    try:
        payload = tomllib.loads(config.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return isinstance((payload.get("plugins") or {}).get(PLUGIN_SELECTOR), dict)


__all__ = [
    "MARKETPLACE_NAME",
    "PLUGIN_NAME",
    "PLUGIN_SELECTOR",
    "find_codex_executable",
    "native_plugin_configured",
]
