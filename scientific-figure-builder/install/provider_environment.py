"""Environment variables forwarded to every supported MCP host.

The default list covers configuration and model-role overrides plus the common
OpenAI/Anthropic credentials. Provider-specific ``key_env`` names declared in the
user config are appended dynamically, so a project can use any provider without
editing the install scripts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

for _parent in Path(__file__).resolve().parents:
    if (_parent / "figure_tools").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from figure_tools.install_paths import APP_NAME, PathEnvironment  # noqa: E402

DEFAULT_ENV_VARS = (
    "SCIENTIFIC_FIGURE_CONFIG",
    "SCIENTIFIC_FIGURE_PROJECT_DIR",
    "SCIENTIFIC_FIGURE_CACHE_DIR",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "SCI_FIG_IMAGE_GENERATE",
    "SCI_FIG_IMAGE_EDIT",
    "SCI_FIG_VISION_ANALYZE",
    "SCI_FIG_VISION_VALIDATE",
)


def _user_config_path() -> Path:
    explicit = os.environ.get("SCIENTIFIC_FIGURE_CONFIG")
    if explicit:
        return Path(explicit)
    return PathEnvironment.from_environ().config_root / APP_NAME / "config.yaml"


def configured_key_envs() -> tuple[str, ...]:
    """Defaults plus any provider ``key_env`` names declared in the user config."""
    names = list(DEFAULT_ENV_VARS)
    try:
        import yaml

        path = _user_config_path()
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            providers = data.get("providers") if isinstance(data, dict) else None
            if isinstance(providers, dict):
                for provider in providers.values():
                    if isinstance(provider, dict) and provider.get("key_env"):
                        names.append(str(provider["key_env"]))
    except Exception:
        pass
    return tuple(dict.fromkeys(names))


PROVIDER_ENV_VARS = configured_key_envs()
