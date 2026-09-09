#!/bin/sh
set -eu

# Scope-aware uninstaller. It preserves user configuration and credentials by
# default; --config/--all explicitly removes only this tool's Keyring entries.
REPOSITORY_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PACKAGE_DIR="$REPOSITORY_DIR/scientific-figure-builder"

if ! command -v uv >/dev/null 2>&1; then
  echo "Uninstall failed: uv is required (https://docs.astral.sh/uv/)." >&2
  exit 1
fi

exec uv run --frozen --directory "$PACKAGE_DIR" \
  python -m install.uninstall_delivery "$@"
