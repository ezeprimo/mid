#!/usr/bin/env bash
set -euo pipefail

# Build Linux release binary with PyInstaller.
# Produces mid-linux-amd64 in OUTPUT_DIR.
#
# Prefer scripts/build-linux-manylinux.sh for release builds: it pins the
# glibc floor by building inside a manylinux_2_28 container (issue #57).
# Building on a modern host produces a binary that only runs on hosts with
# that same glibc or newer.

CLEAN=0
VERSION=""
OUTPUT_DIR="dist"

while (($# > 0)); do
  case "$1" in
    --clean)
      CLEAN=1
      ;;
    --version)
      if [[ -z "${2:-}" ]]; then
        echo "error: --version requires a value" >&2
        exit 2
      fi
      VERSION="${2:-}"
      shift
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift
      ;;
    *)
      echo "error: unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

if [[ -z "$OUTPUT_DIR" ]]; then
  echo "error: --output-dir requires a non-empty value" >&2
  exit 2
fi

normalize_version() {
  local v="$1"
  if [[ "$v" == v* ]]; then
    printf '%s' "${v#v}"
    return
  fi
  printf '%s' "$v"
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [[ -n "${MID_BUILD_PYTHON:-}" ]]; then
  if [[ ! -x "$MID_BUILD_PYTHON" ]]; then
    echo "error: MID_BUILD_PYTHON does not point to an executable: $MID_BUILD_PYTHON" >&2
    exit 2
  fi
  PYTHON="$MID_BUILD_PYTHON"
elif [[ -f "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON="$REPO_ROOT/.venv/bin/python"
else
  PYTHON="python"
fi

EXPECTED_VERSION="$(normalize_version "$VERSION")"
PACKAGE_VERSION="$("$PYTHON" -c "from pathlib import Path; ns={}; exec(Path('src/mid/__init__.py').read_text(encoding='utf-8'), ns); print(ns['__version__'])")"

if [[ -n "$EXPECTED_VERSION" && "$EXPECTED_VERSION" != "$PACKAGE_VERSION" ]]; then
  echo "error: version mismatch: expected $EXPECTED_VERSION but package is $PACKAGE_VERSION" >&2
  exit 1
fi

if [[ "$CLEAN" -eq 1 || -d build || -d "$OUTPUT_DIR" ]]; then
  echo "Cleaning previous build artifacts..."
  rm -rf build "$OUTPUT_DIR" mid-linux-amd64.spec
fi

mkdir -p "$OUTPUT_DIR"
echo "Building mid-linux-amd64 ..."

"$PYTHON" -m PyInstaller --onefile --name mid-linux-amd64 --clean \
  --paths src \
  --hidden-import markitdown \
  --hidden-import numpy._core._exceptions \
  --collect-data magika \
  --exclude-module torch \
  --exclude-module tensorflow \
  --exclude-module transformers \
  --exclude-module scipy \
  --exclude-module matplotlib \
  --exclude-module IPython \
  --exclude-module jedi \
  --exclude-module zmq \
  --exclude-module pytest \
  --distpath "$OUTPUT_DIR" \
  --workpath build \
  --specpath . \
  src/mid/__main__.py

chmod +x "$OUTPUT_DIR/mid-linux-amd64"
echo "SUCCESS: $OUTPUT_DIR/mid-linux-amd64 created"
