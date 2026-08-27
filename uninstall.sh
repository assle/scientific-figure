#!/bin/sh
set -eu

# Scope-aware uninstaller. It preserves user configuration and credentials by
# default; --config/--all explicitly removes only this tool's Keyring entries.
REPOSITORY_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$REPOSITORY_DIR/scientific-figure-builder/install/uninstall_delivery.py" "$@"
