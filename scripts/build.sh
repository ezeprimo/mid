#!/usr/bin/env bash
set -euo pipefail

# Build Linux release binary with PyInstaller.
# Produces mid-linux-amd64 in OUTPUT_DIR.

CLEAN=0
VERSION=""
OUTPUT_DIR="dist"

while (($# > 0)); do
  case "$1" in
    --clean)
      CLEAN=1
      ;;
    --version)
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

EXPECTED_VERSION="$(normalize_version "$VERSION")"
PACKAGE_VERSION="$(python -c "from pathlib import Path; ns={}; exec(Path('src/mid/__init__.py').read_text(encoding='utf-8'), ns); print(ns['__version__'])")"

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

python -m PyInstaller --onefile --name mid-linux-amd64 --clean \
  --paths src \
  --hidden-import markitdown \
  --exclude-module torch \
  --exclude-module tensorflow \
  --exclude-module transformers \
  --exclude-module scipy \
  --exclude-module matplotlib \
  --exclude-module IPython \
  --exclude-module jedi \
  --exclude-module zmq \
  --exclude-module pytest \
  --exclude-module onnxruntime \
  --distpath "$OUTPUT_DIR" \
  --workpath build \
  --specpath . \
  src/mid/__main__.py

chmod +x "$OUTPUT_DIR/mid-linux-amd64"
echo "SUCCESS: $OUTPUT_DIR/mid-linux-amd64 created"
