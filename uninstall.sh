#!/bin/sh
set -eu

# Scope-aware uninstaller. It preserves user configuration and credentials by
# default; --config/--all explicitly removes only this tool's Keyring entries.
REPOSITORY_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PACKAGE_DIR="$REPOSITORY_DIR/scientific-figure-builder"
PYTHONPATH="$PACKAGE_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH

exec python3 -m install.uninstall_delivery "$@"
