#!/bin/sh
set -eu

PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if ! command -v uv >/dev/null 2>&1; then
  echo "Installation failed: uv is required (https://docs.astral.sh/uv/)." >&2
  exit 1
fi

exec uv run --frozen --directory "$PACKAGE_DIR" \
  python -m install.install_delivery --source-dir "$PACKAGE_DIR" "$@"
