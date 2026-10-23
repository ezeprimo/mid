#!/usr/bin/env bash
set -euo pipefail

# Build the Linux release binary inside a manylinux_2_28 container.
#
# Rationale (issue #57): PyInstaller does not bundle glibc, so the produced
# binary can only run on hosts whose glibc is at least as new as the glibc of
# the build host. Building on a GitHub `ubuntu-latest` runner (Ubuntu 24.04,
# glibc 2.39) produced a binary requiring GLIBC 2.38, which aborts on Ubuntu
# 22.04 (2.35) and Debian 12 (2.36).
#
# manylinux_2_28 pins the build glibc to 2.28, so the binary's implicit floor
# becomes glibc >= 2.28 (Debian 10+, Ubuntu 20.04+, Debian 12, ...) without
# depending on a deprecated GitHub runner image (ubuntu-22.04 is unsupported
# after April 2027).

IMAGE="${MID_LINUX_BUILD_IMAGE:-quay.io/pypa/manylinux_2_28_x86_64}"
PYTHON_DIR="/opt/python/cp312-cp312/bin"
GLIBC_FLOOR="2.28"
CONTAINER_ROOT="/work"

CLEAN=0
VERSION=""
OUTPUT_DIR="dist"
PRINT_COMMAND=0

usage_error() {
  echo "error: $1" >&2
  exit 2
}

require_value() {
  local option="$1"
  local value="${2:-}"
  if [[ -z "$value" ]]; then
    usage_error "$option requires a value"
  fi
}

while (($# > 0)); do
  case "$1" in
    --clean)
      CLEAN=1
      ;;
    --version)
      require_value "$1" "${2:-}"
      VERSION="$2"
      shift
      ;;
    --output-dir)
      require_value "$1" "${2:-}"
      OUTPUT_DIR="$2"
      shift
      ;;
    --image)
      require_value "$1" "${2:-}"
      IMAGE="$2"
      shift
      ;;
    --print-command)
      PRINT_COMMAND=1
      ;;
    *)
      usage_error "unknown option: $1"
      ;;
  esac
  shift
done

if [[ -z "$OUTPUT_DIR" ]]; then
  usage_error "--output-dir requires a non-empty value"
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# The output directory must live inside the repository: it is the only path the
# container can write back to the host through the bind mount.
if [[ "$OUTPUT_DIR" = /* ]]; then
  HOST_OUTPUT_DIR="$OUTPUT_DIR"
else
  HOST_OUTPUT_DIR="$REPO_ROOT/$OUTPUT_DIR"
fi

case "$HOST_OUTPUT_DIR" in
  "$REPO_ROOT"/*)
    CONTAINER_OUTPUT_DIR="$CONTAINER_ROOT/${HOST_OUTPUT_DIR#"$REPO_ROOT"/}"
    ;;
  *)
    usage_error "--output-dir must stay inside the repository ($REPO_ROOT): $OUTPUT_DIR"
    ;;
esac

BUILD_ARGS=()
if [[ "$CLEAN" -eq 1 ]]; then
  BUILD_ARGS+=("--clean")
fi
if [[ -n "$VERSION" ]]; then
  BUILD_ARGS+=("--version" "$VERSION")
fi
BUILD_ARGS+=("--output-dir" "$CONTAINER_OUTPUT_DIR")

INNER_COMMAND="set -euo pipefail
export HOME=/tmp
export PATH=${PYTHON_DIR}:\$PATH
python -m venv /tmp/mid-build-venv
/tmp/mid-build-venv/bin/python -m pip install --upgrade --quiet pip
/tmp/mid-build-venv/bin/python -m pip install --quiet 'pyinstaller==6.11.0' 'markitdown[all]'
MID_BUILD_PYTHON=/tmp/mid-build-venv/bin/python bash scripts/build.sh ${BUILD_ARGS[*]}"

DOCKER_ARGS=(
  run --rm
  --user "$(id -u):$(id -g)"
  -v "$REPO_ROOT:$CONTAINER_ROOT"
  -w "$CONTAINER_ROOT"
  -e "HOME=/tmp"
  "$IMAGE"
  bash -lc "$INNER_COMMAND"
)

if [[ "$PRINT_COMMAND" -eq 1 ]]; then
  printf 'docker %s\n' "${DOCKER_ARGS[*]}"
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker is required to build the Linux binary in the manylinux container" >&2
  echo "       install docker or build inside $IMAGE manually" >&2
  exit 1
fi

echo "Building mid-linux-amd64 in $IMAGE (glibc floor $GLIBC_FLOOR) ..."
docker "${DOCKER_ARGS[@]}"

if [[ ! -f "$HOST_OUTPUT_DIR/mid-linux-amd64" ]]; then
  echo "error: expected $HOST_OUTPUT_DIR/mid-linux-amd64 was not produced" >&2
  exit 1
fi

echo "SUCCESS: $HOST_OUTPUT_DIR/mid-linux-amd64 created (glibc >= $GLIBC_FLOOR)"
