"""Narrow Keyring cleanup used only by the explicit config uninstall path."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from figure_tools.providers.auth import KEYRING_SERVICE
except ModuleNotFoundError:  # direct source execution before package path setup
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from figure_tools.providers.auth import KEYRING_SERVICE


def _ids(config_path: Path) -> list[str] | None:
    if not config_path.is_file():
        return []
    try:
        import yaml
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    providers = data.get("providers", {}) if isinstance(data, dict) else {}
    return sorted({
        str(value["credential_id"])
        for value in providers.values()
        if isinstance(value, dict) and value.get("credential_id")
    }) if isinstance(providers, dict) else []


def cleanup_keyring_credentials(
    config_path: Path, *, dry_run: bool = False, runtime_dir: Path | None = None,
) -> tuple[bool, str | None]:
    ids = _ids(config_path)
    if ids is None:
        return False, "Global config could not be read; it was retained"
    if dry_run or not ids:
        return True, None
    try:
        import keyring
    except Exception:
        keyring = None
        if runtime_dir is not None:
            candidates = sorted(
                list((runtime_dir / ".venv" / "lib").glob("python*/site-packages"))
                + [runtime_dir / ".venv" / "Lib" / "site-packages"]
            )
            for candidate in candidates:
                if str(candidate) not in sys.path:
                    sys.path.insert(0, str(candidate))
            try:
                import keyring as runtime_keyring
            except Exception:
                runtime_keyring = None
            keyring = runtime_keyring
        if keyring is None:
            return False, "Keyring backend unavailable; no credentials were removed"
    for credential_id in ids:
        try:
            keyring.delete_password(KEYRING_SERVICE, credential_id)
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ in {"PasswordDeleteError", "NotFoundError"}:
                continue
            return False, "Keyring cleanup failed; user config was retained"
    return True, None


__all__ = ["cleanup_keyring_credentials"]
