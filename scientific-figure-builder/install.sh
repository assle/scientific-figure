#!/bin/sh
set -eu

PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}

exec "$PYTHON_BIN" "$PACKAGE_DIR/install/install_delivery.py" \
  --source-dir "$PACKAGE_DIR" "$@"
