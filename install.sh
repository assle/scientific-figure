#!/bin/sh
set -eu

REPOSITORY_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BOOTSTRAP_REPO=${SCIENTIFIC_FIGURE_BOOTSTRAP_REPO:-assle/scientific-figure}
BOOTSTRAP_REF=${SCIENTIFIC_FIGURE_BOOTSTRAP_REF:-main}

if [ ! -f "$REPOSITORY_DIR/scientific-figure-builder/install.sh" ]; then
  BOOTSTRAP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/scientific-figure.XXXXXX")
  cleanup_bootstrap() {
    rm -rf "$BOOTSTRAP_DIR"
  }
  trap cleanup_bootstrap EXIT HUP INT TERM
  curl -fsSL "https://codeload.github.com/$BOOTSTRAP_REPO/tar.gz/$BOOTSTRAP_REF" |
    tar -xzf - -C "$BOOTSTRAP_DIR" --strip-components=1
  "$BOOTSTRAP_DIR/install.sh" "$@"
  exit $?
fi

exec "$REPOSITORY_DIR/scientific-figure-builder/install.sh" "$@"
