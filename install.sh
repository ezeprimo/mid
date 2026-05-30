#!/usr/bin/env bash
set -euo pipefail

REPO="${MID_REPO:-ezeprimo/mid}"
API_BASE="${MID_API_BASE:-https://api.github.com}"
RAW_BASE="${MID_RAW_BASE:-https://raw.githubusercontent.com}"
REQUESTED_VERSION_RAW="${MID_VERSION:-latest}"
if [[ -z "${REQUESTED_VERSION_RAW}" ]]; then
  REQUESTED_VERSION_RAW="latest"
fi

ASSET_NAME="mid-linux-amd64"
CHECKSUMS_ASSET_NAME="checksums.txt"
INSTALL_DIR="${MID_INSTALL_DIR:-$HOME/.local/bin}"
TARGET_PATH="$INSTALL_DIR/mid"
PROFILE_FILE="$HOME/.profile"
STANZA_BEGIN="# >>> mid installer path >>>"
STANZA_END="# <<< mid installer path <<<"
SMOKE_PATTERN="${MID_SMOKE_PATTERN:-mid}"
DISABLE_PERSIST_PATH_UPDATE="${MID_DISABLE_PERSIST_PATH_UPDATE:-0}"
PYTHON_BIN="${MID_PYTHON_BIN:-python}"

normalize_requested_version() {
  local value="$1"
  if [[ "$value" == "latest" ]]; then
    printf '%s' "latest"
    return
  fi
  if [[ "$value" == v* ]]; then
    printf '%s' "$value"
    return
  fi
  printf 'v%s' "$value"
}

github_api_get() {
  local url="$1"
  curl -fsSL \
    -H "Accept: application/vnd.github+json" \
    -H "User-Agent: mid-installer" \
    "$url"
}

extract_json_field() {
  local release_json_path="$1"
  local field="$2"
  "$PYTHON_BIN" - "$release_json_path" "$field" <<'PY'
import json
import sys
from pathlib import Path

release_path = Path(sys.argv[1])
field_name = sys.argv[2]
data = json.loads(release_path.read_text(encoding="utf-8"))
value = data.get(field_name, "")
if value is None:
    value = ""
print(value)
PY
}

asset_url_from_release_json() {
  local release_json_path="$1"
  local required_name="$2"
  "$PYTHON_BIN" - "$release_json_path" "$required_name" <<'PY'
import json
import sys
from pathlib import Path

release_path = Path(sys.argv[1])
required = sys.argv[2]
payload = json.loads(release_path.read_text(encoding="utf-8"))

for asset in payload.get("assets", []):
    if asset.get("name") == required:
        print(asset.get("browser_download_url", ""))
        sys.exit(0)

sys.exit(1)
PY
}

show_fallback_guidance() {
  local resolved_tag="$1"
  local reason="$2"
  local package_version="${resolved_tag#v}"
  local install_script_url="$RAW_BASE/$REPO/$resolved_tag/install.sh"

  echo "WARNING: Binary install stopped: $reason" >&2
  echo
  echo "Fallback with the same version target ($resolved_tag):"
  echo "  pipx install --force 'mid==$package_version'"
  echo "  python -m pip install --user 'mid==$package_version'"
  echo
  echo "Update to latest stable:"
  echo "  unset MID_VERSION"
  echo "  curl -fsSL $install_script_url | bash"
  echo
  echo "Rollback to a pinned version:"
  echo "  MID_VERSION=vX.Y.Z curl -fsSL $install_script_url | bash"
  echo
  echo "Phase-1 uninstall:"
  echo "  rm -f '$TARGET_PATH'"
  echo "  Remove '$INSTALL_DIR' from PATH and delete installer stanza in $PROFILE_FILE if present"
}

ensure_path_stanza() {
  local install_dir="$1"
  local profile="$2"
  local line="export PATH=\"$install_dir:\$PATH\""

  if [[ "$DISABLE_PERSIST_PATH_UPDATE" == "1" ]]; then
    return 1
  fi

  if [[ -w "$profile" || ! -e "$profile" ]]; then
    mkdir -p "$(dirname "$profile")"
    touch "$profile"

    if grep -Fq "$STANZA_BEGIN" "$profile"; then
      return 0
    fi

    {
      echo
      echo "$STANZA_BEGIN"
      echo "$line"
      echo "$STANZA_END"
    } >> "$profile"
    return 0
  fi

  return 1
}

REQUESTED_VERSION="$(normalize_requested_version "$REQUESTED_VERSION_RAW")"
RELEASE_API_URL=""
if [[ "$REQUESTED_VERSION" == "latest" ]]; then
  RELEASE_API_URL="$API_BASE/repos/$REPO/releases/latest"
else
  RELEASE_API_URL="$API_BASE/repos/$REPO/releases/tags/$REQUESTED_VERSION"
fi

TEMP_ROOT="$(mktemp -d 2>/dev/null || mktemp -d -t mid-installer)"
trap 'rm -rf "$TEMP_ROOT"' EXIT

RELEASE_JSON="$TEMP_ROOT/release.json"
BINARY_PATH="$TEMP_ROOT/$ASSET_NAME"
CHECKSUMS_PATH="$TEMP_ROOT/$CHECKSUMS_ASSET_NAME"

if ! github_api_get "$RELEASE_API_URL" > "$RELEASE_JSON"; then
  echo "ERROR: Unable to resolve release '$REQUESTED_VERSION' from '$REPO'." >&2
  exit 1
fi

RESOLVED_TAG="$(extract_json_field "$RELEASE_JSON" tag_name)"
if [[ -z "$RESOLVED_TAG" ]]; then
  echo "ERROR: Resolved release is missing tag_name." >&2
  exit 1
fi

if [[ "$REQUESTED_VERSION" != "latest" && "$RESOLVED_TAG" != "$REQUESTED_VERSION" ]]; then
  echo "ERROR: Resolved tag '$RESOLVED_TAG' does not match requested '$REQUESTED_VERSION'." >&2
  exit 1
fi

if ! BINARY_URL="$(asset_url_from_release_json "$RELEASE_JSON" "$ASSET_NAME")"; then
  echo "ERROR: Release $RESOLVED_TAG is missing asset '$ASSET_NAME'." >&2
  exit 1
fi

if ! CHECKSUMS_URL="$(asset_url_from_release_json "$RELEASE_JSON" "$CHECKSUMS_ASSET_NAME")"; then
  echo "ERROR: Release $RESOLVED_TAG is missing asset '$CHECKSUMS_ASSET_NAME'." >&2
  exit 1
fi

curl -fsSL "$BINARY_URL" -o "$BINARY_PATH"
curl -fsSL "$CHECKSUMS_URL" -o "$CHECKSUMS_PATH"

EXPECTED_HASH="$(awk -v n="$ASSET_NAME" '{name=$2; gsub(/\r/, "", name); if (name==n) print tolower($1)}' "$CHECKSUMS_PATH" | head -n 1)"
if [[ -z "$EXPECTED_HASH" ]]; then
  show_fallback_guidance "$RESOLVED_TAG" "checksums.txt is missing an entry for '$ASSET_NAME'."
  exit 1
fi

ACTUAL_HASH="$(sha256sum "$BINARY_PATH" | awk '{print tolower($1)}')"
if [[ "$EXPECTED_HASH" != "$ACTUAL_HASH" ]]; then
  show_fallback_guidance "$RESOLVED_TAG" "SHA-256 mismatch for $ASSET_NAME"
  exit 1
fi

chmod +x "$BINARY_PATH"

if ! VERSION_OUTPUT="$($BINARY_PATH --version 2>&1)"; then
  show_fallback_guidance "$RESOLVED_TAG" "Binary smoke check failed (--version): $VERSION_OUTPUT"
  exit 1
fi

if [[ "$VERSION_OUTPUT" != *"$SMOKE_PATTERN"* ]]; then
  show_fallback_guidance "$RESOLVED_TAG" "Unexpected binary output during smoke check."
  exit 1
fi

mkdir -p "$INSTALL_DIR"
TMP_TARGET="$INSTALL_DIR/.mid.tmp.$$"
cp "$BINARY_PATH" "$TMP_TARGET"
chmod +x "$TMP_TARGET"
mv -f "$TMP_TARGET" "$TARGET_PATH"

PATH_UPDATED="false"
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
  export PATH="$INSTALL_DIR:$PATH"
fi

if ensure_path_stanza "$INSTALL_DIR" "$PROFILE_FILE"; then
  PATH_UPDATED="true"
fi

echo "Installed mid $RESOLVED_TAG to $TARGET_PATH"
if [[ "$PATH_UPDATED" == "true" ]]; then
  echo "Ensured persistent PATH stanza in $PROFILE_FILE. Open a new shell before running 'mid'."
else
  echo "WARNING: Could not update $PROFILE_FILE automatically." >&2
  echo "Add this line manually and open a new shell:" >&2
  echo "  export PATH=\"$INSTALL_DIR:\$PATH\"" >&2
fi

INSTALL_SCRIPT_URL="$RAW_BASE/$REPO/$RESOLVED_TAG/install.sh"
echo
echo "Update to latest stable:"
echo "  unset MID_VERSION"
echo "  curl -fsSL $INSTALL_SCRIPT_URL | bash"
echo
echo "Rollback to a pinned version:"
echo "  MID_VERSION=vX.Y.Z curl -fsSL $INSTALL_SCRIPT_URL | bash"
echo
echo "Phase-1 uninstall:"
echo "  rm -f '$TARGET_PATH'"
echo "  Remove '$INSTALL_DIR' from PATH and delete installer stanza in $PROFILE_FILE if present"
