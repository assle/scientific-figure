"""Provider credential helpers (plan section 5).

The API key is read from an environment variable or a user-private file and is
never written to a repository, report, prompt log, or run manifest.
"""

from __future__ import annotations

import os
from pathlib import Path

REDACTED = "***REDACTED***"


def get_api_key(
    env_var: str = "SCIENTIFIC_FIGURE_API_KEY",
    file_path: str | Path | None = None,
) -> str | None:
    if env_var in os.environ:
        return os.environ[env_var]
    if file_path is not None:
        path = Path(file_path)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return None


def redact(text: str, key: str | None) -> str:
    if key and key in text:
        return text.replace(key, REDACTED)
    return text
