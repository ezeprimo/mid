#!/usr/bin/env bash
set -euo pipefail

RUNTIME="opencode"
MODE="copy"
DESTINATION=""

usage() {
  cat <<'EOF'
Install the repo-local mid-cli skill into a supported agent skills directory.

Usage:
  bash ./scripts/install-skill.sh [opencode|claude|agents|all] [--mode copy|symlink] [--dest PATH]

Examples:
  bash ./scripts/install-skill.sh opencode
  bash ./scripts/install-skill.sh claude --mode symlink
  bash ./scripts/install-skill.sh all --mode copy
EOF
}

while (($# > 0)); do
  case "$1" in
    opencode|claude|agents|all)
      RUNTIME="$1"
      ;;
    --mode)
      MODE="${2:-}"
      shift
      ;;
    --dest)
      DESTINATION="${2:-}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "$MODE" != "copy" && "$MODE" != "symlink" ]]; then
  echo "error: --mode must be 'copy' or 'symlink'" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$REPO_ROOT/skills/mid-cli"

if [[ ! -f "$SOURCE_DIR/SKILL.md" ]]; then
  echo "error: source skill not found at $SOURCE_DIR" >&2
  exit 1
fi

install_one() {
  local runtime="$1"
  local base_dir="$2"
  local target_dir
  target_dir="$base_dir/mid-cli"

  mkdir -p "$base_dir"

  if [[ -e "$target_dir" || -L "$target_dir" ]]; then
    rm -rf "$target_dir"
  fi

  if [[ "$MODE" == "symlink" ]]; then
    ln -s "$SOURCE_DIR" "$target_dir"
  else
    cp -R "$SOURCE_DIR" "$target_dir"
  fi

  echo "Installed mid-cli skill for $runtime -> $target_dir ($MODE)"
}

default_dir_for() {
  case "$1" in
    opencode) printf '%s' "$HOME/.config/opencode/skills" ;;
    claude) printf '%s' "$HOME/.claude/skills" ;;
    agents) printf '%s' "$HOME/.agents/skills" ;;
    *) return 1 ;;
  esac
}

if [[ -n "$DESTINATION" && "$RUNTIME" == "all" ]]; then
  echo "error: --dest cannot be used with runtime 'all'" >&2
  exit 2
fi

if [[ "$RUNTIME" == "all" ]]; then
  install_one "opencode" "$(default_dir_for opencode)"
  install_one "claude" "$(default_dir_for claude)"
  install_one "agents" "$(default_dir_for agents)"
  exit 0
fi

TARGET_BASE="${DESTINATION:-$(default_dir_for "$RUNTIME")}"
install_one "$RUNTIME" "$TARGET_BASE"
