#!/bin/sh
set -eu

PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}

PYTHONPATH="$PACKAGE_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH

exec "$PYTHON_BIN" -m install.install_delivery \
  --source-dir "$PACKAGE_DIR" "$@"
