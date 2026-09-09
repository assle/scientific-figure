#!/bin/sh
set -eu

REPOSITORY_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BOOTSTRAP_REPO=${SCIENTIFIC_FIGURE_BOOTSTRAP_REPO:-assle/scientific-figure}
BOOTSTRAP_REF=${SCIENTIFIC_FIGURE_BOOTSTRAP_REF:-main}

ACTIVATE_RELEASE=0
REQUEST_CODEX=0
REQUEST_VERIFY=0
for argument in "$@"; do
  case "$argument" in
    --release|--latest|--bundle)
      ACTIVATE_RELEASE=1
      ;;
    --codex)
      REQUEST_CODEX=1
      ;;
    --verify)
      REQUEST_VERIFY=1
      ;;
  esac
done

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

if [ "$ACTIVATE_RELEASE" -eq 1 ] || { [ "$REQUEST_CODEX" -eq 1 ] && [ "$REQUEST_VERIFY" -eq 1 ]; }; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "Installation failed: uv is required (https://docs.astral.sh/uv/)." >&2
    exit 1
  fi
fi

if [ "$ACTIVATE_RELEASE" -eq 1 ]; then
  SCIENTIFIC_FIGURE_CALLER_CWD=$(pwd)
  export SCIENTIFIC_FIGURE_CALLER_CWD
  exec uv run --frozen --directory "$REPOSITORY_DIR/scientific-figure-builder" \
    python -m figure_tools update "$@"
fi

if [ "$REQUEST_CODEX" -eq 1 ] && [ "$REQUEST_VERIFY" -eq 1 ]; then
  exec uv run --frozen --directory "$REPOSITORY_DIR/scientific-figure-builder" \
    python -m figure_tools status --verbose
fi

if [ "$REQUEST_CODEX" -eq 1 ]; then
  echo "Installation failed: --codex now performs complete activation and requires --release VERSION, --latest, or --bundle FILE. Use --runtime-only for Core only." >&2
  exit 2
fi

exec "$REPOSITORY_DIR/scientific-figure-builder/install.sh" "$@"
