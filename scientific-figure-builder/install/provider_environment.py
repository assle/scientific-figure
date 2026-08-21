"""Environment variables forwarded to every supported MCP host.

The default list covers configuration and model-role overrides plus the common
OpenAI/Anthropic credentials. Provider-specific ``key_env`` names declared in the
user config are appended dynamically, so a project can use any provider without
editing the install scripts.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_VARS = (
    "SCIENTIFIC_FIGURE_CONFIG",
    "SCIENTIFIC_FIGURE_PROJECT_DIR",
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
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "scientific-figure-builder" / "config.yaml"


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
