"""Narrow Keyring cleanup used only by the explicit config uninstall path."""

from __future__ import annotations

from pathlib import Path

SERVICE = "scientific-figure-builder"


def _ids(config_path: Path) -> list[str]:
    if not config_path.is_file():
        return []
    try:
        import yaml
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    providers = data.get("providers", {}) if isinstance(data, dict) else {}
    return sorted({
        str(value["credential_id"])
        for value in providers.values()
        if isinstance(value, dict) and value.get("credential_id")
    }) if isinstance(providers, dict) else []


def cleanup_keyring_credentials(config_path: Path, *, dry_run: bool = False) -> tuple[bool, str | None]:
    ids = _ids(config_path)
    if dry_run or not ids:
        return True, None
    try:
        import keyring
    except Exception:
        return False, "Keyring backend unavailable; no credentials were removed"
    for credential_id in ids:
        try:
            keyring.delete_password(SERVICE, credential_id)
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ in {"PasswordDeleteError", "NotFoundError"}:
                continue
            return False, "Keyring cleanup failed; user config was retained"
    return True, None


__all__ = ["cleanup_keyring_credentials"]
