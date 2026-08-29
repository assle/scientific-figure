"""Narrow Keyring cleanup used only by the explicit config uninstall path."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
        if runtime_dir is not None:
            runtime_result = _cleanup_with_runtime(runtime_dir, ids)
            if runtime_result:
                return True, None
        return False, "Keyring backend unavailable; no credentials were removed"
    for credential_id in ids:
        try:
            keyring.delete_password(KEYRING_SERVICE, credential_id)
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ in {"PasswordDeleteError", "NotFoundError"}:
                continue
            return False, "Keyring cleanup failed; user config was retained"
    return True, None


def _cleanup_with_runtime(runtime_dir: Path, credential_ids: list[str]) -> bool:
    candidates = (
        runtime_dir / ".venv" / "bin" / "python",
        runtime_dir / ".venv" / "Scripts" / "python.exe",
    )
    runtime_python = next((path for path in candidates if path.is_file()), None)
    if runtime_python is None:
        return False
    code = (
        "import json,keyring,sys\n"
        "for credential_id in json.loads(sys.argv[2]):\n"
        "  try:\n"
        "    keyring.delete_password(sys.argv[1], credential_id)\n"
        "  except Exception as exc:\n"
        "    if type(exc).__name__ not in {'PasswordDeleteError','NotFoundError'}: raise\n"
    )
    result = subprocess.run(
        [str(runtime_python), "-c", code, KEYRING_SERVICE, json.dumps(credential_ids)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


__all__ = ["cleanup_keyring_credentials"]
