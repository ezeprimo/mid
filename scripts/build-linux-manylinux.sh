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
#
# The image is pinned by digest because the tag is mutable: an upstream retag
# would silently change the toolchain and the dependency resolution of a
# release that claims a specific glibc floor. Bump the digest deliberately:
#   docker pull quay.io/pypa/manylinux_2_28_x86_64
#   docker inspect --format '{{index .RepoDigests 0}}' quay.io/pypa/manylinux_2_28_x86_64
IMAGE="${MID_LINUX_BUILD_IMAGE:-quay.io/pypa/manylinux_2_28_x86_64@sha256:076b19ef6e698f28649fa817c49d14443201e01da85240e8e52f93e8daa49bff}"
PYTHON_DIR="/opt/python/cp312-cp312/bin"
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

# The claimed glibc floor must come from the image actually used, never from a
# constant that could drift away from it.
if [[ ! "$IMAGE" =~ manylinux_2_([0-9]+) ]]; then
  usage_error "--image must be a manylinux_2_<glibc-minor> image: $IMAGE"
fi
GLIBC_FLOOR="2.${BASH_REMATCH[1]}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# Resolve both sides before comparing: a textual prefix test lets `..` (or a
# symlinked path) escape the bind mount, after which the build is discarded
# when the container exits and a stale host file could report false success.
REPO_ROOT_REAL="$(realpath -- "$REPO_ROOT")"
if [[ "$OUTPUT_DIR" = /* ]]; then
  RESOLVED_OUTPUT_DIR="$OUTPUT_DIR"
else
  RESOLVED_OUTPUT_DIR="$REPO_ROOT_REAL/$OUTPUT_DIR"
fi
HOST_OUTPUT_DIR="$(realpath -m -- "$RESOLVED_OUTPUT_DIR")"

case "$HOST_OUTPUT_DIR" in
  "$REPO_ROOT_REAL"/?*)
    CONTAINER_OUTPUT_DIR="$CONTAINER_ROOT/${HOST_OUTPUT_DIR#"$REPO_ROOT_REAL"/}"
    ;;
  *)
    usage_error "--output-dir must be a directory inside the repository ($REPO_ROOT_REAL): $OUTPUT_DIR"
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

# The build arguments are forwarded positionally ("$@"), never interpolated
# into a shell string: a value with spaces or shell metacharacters would
# otherwise run as commands inside a container that has the repository
# bind-mounted read-write.
INNER_COMMAND="set -euo pipefail
export HOME=/tmp
export PATH=${PYTHON_DIR}:\$PATH
python -m venv /tmp/mid-build-venv
/tmp/mid-build-venv/bin/python -m pip install --upgrade --quiet pip
/tmp/mid-build-venv/bin/python -m pip install --quiet 'pyinstaller==6.11.0' 'markitdown[all]'
MID_BUILD_PYTHON=/tmp/mid-build-venv/bin/python bash scripts/build.sh \"\$@\""

DOCKER_ARGS=(
  run --rm
  --user "$(id -u):$(id -g)"
  -v "$REPO_ROOT_REAL:$CONTAINER_ROOT"
  -w "$CONTAINER_ROOT"
  -e "HOME=/tmp"
  "$IMAGE"
  bash -lc "$INNER_COMMAND" "_" "${BUILD_ARGS[@]}"
)

if [[ "$PRINT_COMMAND" -eq 1 ]]; then
  printf 'docker'
  printf ' %q' "${DOCKER_ARGS[@]}"
  printf '\n'
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
