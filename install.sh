#!/bin/sh
set -eu

REPOSITORY_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$REPOSITORY_DIR/scientific-figure-builder/install.sh" "$@"
