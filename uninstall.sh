#!/usr/bin/env bash
#
# uninstall.sh — Reverse operation of install.sh
#
# Removes the mid binary, cleans up the PATH stanza from shell profiles,
# and removes install directories if empty.
#
# Safe to run even if mid was partially installed or already removed.
# Reports what was found and what was cleaned.
#
# Environment overrides (same as install.sh):
#   MID_REPO             — GitHub repo (default: ezeprimo/mid), for documentation
#   MID_INSTALL_DIR      — custom install directory (default: $HOME/.local/bin)
#   MID_PROFILE_FILE     — profile file to clean (default: $HOME/.profile); not yet
#                        — supported by install.sh — set manually if needed
#
# Usage:
#   ./uninstall.sh                  # interactive
#   ./uninstall.sh --force          # skip confirmation
#   ./uninstall.sh --dry-run        # preview only
#

# ---- config ----------------------------------------------------------------

REPO="${MID_REPO:-ezeprimo/mid}"
INSTALL_DIR="${MID_INSTALL_DIR:-$HOME/.local/bin}"
TARGET_PATH="$INSTALL_DIR/mid"
PROFILE_FILE="${MID_PROFILE_FILE:-$HOME/.profile}"
STANZA_BEGIN="# >>> mid installer path >>>"
STANZA_END="# <<< mid installer path <<<"

# ---- reusable functions (available when sourced) ---------------------------

REMOVED_SOMETHING=0
FOUND_ISSUES=0

info()  { printf '\e[36m%s\e[0m\n' "$1"; }
ok()    { printf '  \e[32m[removed]\e[0m %s\n' "$1"; REMOVED_SOMETHING=1; }
skip()  { printf '  \e[33m[skipped]\e[0m %s — %s\n' "$1" "$2"; }
absent(){ printf '  \e[90m[absent]\e[0m  %s — nothing to clean\n' "$1"; }
dry()   { printf '  \e[35m[dry-run]\e[0m would %s\n' "$1"; }
warn()  { printf '\e[33mWARNING:\e[0m %s\n' "$1" >&2; FOUND_ISSUES=1; }

# clean_stanza — removes the mid installer stanza from a shell profile file
clean_stanza() {
  local file="$1"
  local temp_file=""

  if [[ ! -f "$file" ]]; then
    return 2   # file doesn't exist
  fi

  temp_file="$(mktemp /tmp/mid-uninstall.XXXXXX 2>/dev/null || mktemp -t mid-uninstall 2>/dev/null)"
  if [[ -z "$temp_file" ]]; then
    warn "Cannot create temp file in /tmp or /tmp/mid-uninstall.XXXXXX — skipping stanza cleanup"
    return 1
  fi

  # Check if stanza exists
  if ! grep -Fq "$STANZA_BEGIN" "$file"; then
    rm -f "$temp_file"
    return 1   # stanza not found
  fi

  # Remove everything between (and including) the begin/end markers
  # Using sed in a way that's compatible across Linux and macOS
  local in_stanza=0
  local removed=0

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "$STANZA_BEGIN" ]]; then
      in_stanza=1
      removed=1
      continue
    fi
    if [[ "$in_stanza" -eq 1 && "$line" == "$STANZA_END" ]]; then
      in_stanza=0
      continue
    fi
    if [[ "$in_stanza" -eq 0 ]]; then
      printf '%s\n' "$line" >> "$temp_file"
    fi
  done < "$file"

  # If we removed something, replace the file
  if [[ "$removed" -eq 1 ]]; then
    cat "$temp_file" > "$file"
    rm -f "$temp_file"
    return 0
  fi

  rm -f "$temp_file"
  return 1
}

# === MAIN ===
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -euo pipefail

  FORCE=0
  DRY_RUN=0

  for arg in "$@"; do
    case "$arg" in
      --force|-f)  FORCE=1 ;;
      --dry-run|-n) DRY_RUN=1 ;;
      --help|-h)
        echo "Usage: $0 [--force] [--dry-run]"
        echo "  --force, -f     Skip confirmation prompt"
        echo "  --dry-run, -n   Preview changes without modifying anything"
        exit 0
        ;;
    esac
  done

  # ---- preamble --------------------------------------------------------------

  echo ""
  echo "╔══════════════════════════════════════════╗"
  echo "║       mid — Uninstall Script (Linux)     ║"
  echo "╚══════════════════════════════════════════╝"
  echo ""
  echo "Install dir : $INSTALL_DIR"
  echo "Binary      : $TARGET_PATH"
  echo "Profile     : $PROFILE_FILE"
  echo ""

  if [[ "$FORCE" -ne 1 && "$DRY_RUN" -ne 1 ]]; then
    printf '\e[33mThis will remove mid from your system.\e[0m\n'
    read -r -p "Continue? [y/N] " REPLY
    if [[ ! "$REPLY" =~ ^[yY] ]]; then
      echo "Uninstall cancelled."
      exit 0
    fi
  fi

  # ---- 1. Remove binary ------------------------------------------------------

  info ""
  info ">> Binary"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    if [[ -f "$TARGET_PATH" ]]; then
      dry "remove '$TARGET_PATH'"
    else
      absent "$TARGET_PATH"
    fi
  else
    if [[ -f "$TARGET_PATH" ]]; then
      rm -f "$TARGET_PATH"
      if [[ ! -f "$TARGET_PATH" ]]; then
        ok "$TARGET_PATH"
      else
        warn "Could not delete '$TARGET_PATH' — permission denied or file busy."
      fi
    else
      absent "$TARGET_PATH"
    fi
  fi

  # ---- 2. Remove install directories (bottom-up) -----------------------------

  info ""
  info ">> Install directories"

  for dir in "$INSTALL_DIR" "$(dirname "$INSTALL_DIR")"; do
    if [[ "$DRY_RUN" -eq 1 ]]; then
      if [[ -d "$dir" ]]; then
        # Collect real entries (exclude . and ..)
        real_contents=()
        for p in "$dir"/* "$dir"/.*; do
          base="$(basename "$p")"
          [[ "$base" == "." || "$base" == ".." ]] && continue
          [[ -e "$p" || -L "$p" ]] && real_contents+=("$p")
        done
        if [[ ${#real_contents[@]} -eq 0 ]]; then
          dry "remove empty directory '$dir'"
        else
          dry "skip non-empty directory '$dir' (${#real_contents[@]} item(s) remain)"
        fi
      fi
      continue
    fi

    if [[ ! -d "$dir" ]]; then
      absent "$dir"
      continue
    fi

    # Count real entries (excluding . and ..)
    entry_count=0
    for entry in "$dir"/* "$dir"/.*; do
      base="$(basename "$entry")"
      [[ "$base" == "." || "$base" == ".." ]] && continue
      if [[ -e "$entry" || -L "$entry" ]]; then
        entry_count=$((entry_count + 1))
      fi
    done

    if [[ "$entry_count" -eq 0 ]]; then
      if rmdir "$dir" 2>/dev/null; then
        ok "empty directory '$dir'"
      else
        skip "$dir" "could not be removed"
      fi
    else
      skip "$dir" "$entry_count item(s) remain — not mid-related"
    fi
  done

  # ---- 3. Remove PATH stanza from profile ------------------------------------

  info ""
  info ">> PATH configuration"

  profile_cleaned=0
  profile_absent=0

  if [[ "$DRY_RUN" -eq 1 ]]; then
    if [[ -f "$PROFILE_FILE" ]] && grep -Fq "$STANZA_BEGIN" "$PROFILE_FILE"; then
      dry "remove mid PATH stanza from '$PROFILE_FILE'"
    else
      absent "mid PATH stanza in '$PROFILE_FILE'"
    fi
  else
    if [[ ! -f "$PROFILE_FILE" ]]; then
      absent "$PROFILE_FILE (no profile to clean)"
    else
      clean_stanza "$PROFILE_FILE" && rc=0 || rc=$?
      if [[ "$rc" -eq 0 ]]; then
        ok "mid PATH stanza removed from '$PROFILE_FILE'"
        profile_cleaned=1
      elif [[ "$rc" -eq 1 ]]; then
        absent "mid PATH stanza in '$PROFILE_FILE'"
      else
        absent "$PROFILE_FILE (file not found)"
      fi
    fi
  fi

  # ---- 4. Clean current session PATH ------------------------------------------
  # The installer added $INSTALL_DIR to the current session; we remove it here.

  info ""
  info ">> Session PATH"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    if [[ ":$PATH:" == *":$INSTALL_DIR:"* ]]; then
      dry "remove '$INSTALL_DIR' from current session PATH"
    else
      absent "'$INSTALL_DIR' in current session PATH"
    fi
  else
    if [[ ":$PATH:" == *":$INSTALL_DIR:"* ]]; then
      # Use bash parameter expansion instead of sed to avoid regex injection (e.g. dots, brackets in path)
      local_clean_path=":$PATH:"
      local_clean_path="${local_clean_path//:$INSTALL_DIR:/:}"
      local_clean_path="${local_clean_path#:}"
      local_clean_path="${local_clean_path%:}"
      export PATH="$local_clean_path"
      ok "'$INSTALL_DIR' removed from current session PATH"
    else
      absent "'$INSTALL_DIR' in current session PATH"
    fi
  fi

  # ---- 5. Check for other profiles (bashrc, zshrc, etc.) ---------------------
  # The installer only writes to $PROFILE_FILE, but users may have sourced it.

  info ""
  info ">> Additional profiles (quick check)"

  for candidate in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.config/fish/config.fish"; do
    if [[ -f "$candidate" ]]; then
      if grep -Fq "$STANZA_BEGIN" "$candidate" 2>/dev/null; then
        if [[ "$DRY_RUN" -eq 1 ]]; then
          dry "remove mid PATH stanza from '$candidate'"
        else
          clean_stanza "$candidate" && ok "mid PATH stanza removed from '$candidate'" || warn "unexpected error cleaning stanza in '$candidate'"
        fi
      fi
    fi
  done

  # ---- 6. Summary ------------------------------------------------------------

  info ""
  info ">> Done"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Dry-run complete — no changes were made."
  elif [[ "$REMOVED_SOMETHING" -eq 1 ]]; then
    echo "mid has been uninstalled."
    if [[ "$FOUND_ISSUES" -eq 1 ]]; then
      warn "Some items could not be cleaned (see warnings above)."
    fi
  else
    echo "Nothing to uninstall — mid was not found in the standard locations."
    echo "If you installed mid to a custom location, remove it manually or set:"
    echo "  MID_INSTALL_DIR=/path/to/custom/dir $0"
  fi

  echo ""
  echo "Reinstall at any time:"
  echo "  curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | bash"
  echo ""
fi
