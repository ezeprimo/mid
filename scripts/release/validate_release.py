"""Release contract validator for mid distribution artifacts.

Validates:
- Required asset names
- Tag/package version alignment
- checksums.txt required entries for installer binaries
- Minimum release-note operator guidance
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SEMVER_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
WHEEL_RE = re.compile(r"^mid-(?P<version>.+)-py3-none-any\.whl$")
SDIST_RE = re.compile(r"^mid-(?P<version>.+)\.tar\.gz$")
CHECKSUM_LINE_RE = re.compile(r"^(?P<sha>[a-fA-F0-9]{64})\s+(?P<name>\S+)$")

REQUIRED_BINARY_ASSETS = ("mid-windows-amd64.exe", "mid-linux-amd64")
REQUIRED_ASSETS = REQUIRED_BINARY_ASSETS + ("checksums.txt",)


def select_latest_stable_release(releases: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Return the newest stable (non-draft, non-prerelease) release."""
    stable: list[tuple[tuple[int, int, int], Mapping[str, Any]]] = []
    for release in releases:
        if bool(release.get("draft")) or bool(release.get("prerelease")):
            continue

        tag = str(release.get("tag_name", ""))
        match = SEMVER_TAG_RE.fullmatch(tag)
        if not match:
            continue

        stable.append(((int(match.group(1)), int(match.group(2)), int(match.group(3))), release))

    if not stable:
        raise ValueError("No stable releases available")

    stable.sort(key=lambda item: item[0], reverse=True)
    return stable[0][1]


def resolve_release_tag(requested: str, releases: Sequence[Mapping[str, Any]]) -> str:
    """Resolve 'latest' or pinned tag to an exact release tag."""
    if requested == "latest":
        latest = select_latest_stable_release(releases)
        return str(latest["tag_name"])

    for release in releases:
        if str(release.get("tag_name", "")) == requested:
            return requested

    raise ValueError(f"Requested release tag not found: {requested}")


def _asset_names(release: Mapping[str, Any]) -> list[str]:
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        return []
    names: list[str] = []
    for asset in assets:
        if isinstance(asset, Mapping):
            names.append(str(asset.get("name", "")))
    return names


def _extract_version(names: Sequence[str], pattern: re.Pattern[str], label: str, errors: list[str]) -> str | None:
    versions: list[str] = []
    for name in names:
        match = pattern.fullmatch(name)
        if match:
            versions.append(match.group("version"))

    if len(versions) != 1:
        errors.append(f"Expected exactly one {label} asset, found {len(versions)}")
        return None
    return versions[0]


def _parse_checksums(checksums_content: str, errors: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in checksums_content.splitlines():
        candidate = line.strip()
        if not candidate:
            continue

        match = CHECKSUM_LINE_RE.fullmatch(candidate)
        if not match:
            errors.append(f"Malformed checksum line: {line}")
            continue

        parsed[match.group("name")] = match.group("sha")

    return parsed


def _validate_required_notes(body: str, errors: list[str]) -> None:
    lowered = body.lower()
    checks = [
        ("Windows install command", "install.ps1" in lowered or "irm " in lowered),
        ("Linux install command", "install.sh" in lowered or "curl -fssl" in lowered),
        ("Version pinning example", "mid_version=v" in lowered),
        ("Fallback instructions", "pipx" in lowered or "pip install" in lowered),
        ("Rollback guidance", "rollback" in lowered or "roll back" in lowered),
    ]

    for section_name, ok in checks:
        if not ok:
            errors.append(f"Release notes missing: {section_name}")


def validate_release_contract(release: Mapping[str, Any]) -> list[str]:
    """Validate one release payload against phase-1 distribution contract."""
    errors: list[str] = []

    tag = str(release.get("tag_name", ""))
    if not tag.startswith("v"):
        errors.append("tag_name must start with 'v'")
    tag_version = tag[1:] if tag.startswith("v") else None

    names = _asset_names(release)
    for required in REQUIRED_ASSETS:
        if required not in names:
            errors.append(f"Missing required asset: {required}")

    wheel_version = _extract_version(names, WHEEL_RE, "wheel", errors)
    sdist_version = _extract_version(names, SDIST_RE, "sdist", errors)

    if tag_version and wheel_version and wheel_version != tag_version:
        errors.append(f"Wheel version mismatch: tag={tag_version}, wheel={wheel_version}")
    if tag_version and sdist_version and sdist_version != tag_version:
        errors.append(f"sdist version mismatch: tag={tag_version}, sdist={sdist_version}")

    checksums_content = release.get("checksums_content")
    if not isinstance(checksums_content, str):
        errors.append("checksums_content is required for checksum validation")
    else:
        checksums = _parse_checksums(checksums_content, errors)
        for required_binary in REQUIRED_BINARY_ASSETS:
            if required_binary not in checksums:
                errors.append(f"Missing checksum entry for {required_binary}")

    body = str(release.get("body", ""))
    _validate_required_notes(body, errors)

    return errors


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate release contract for mid")
    parser.add_argument("--release-json", required=True, help="Path to a single release JSON file")
    parser.add_argument("--requested-tag", default="latest", help="Tag to resolve (default: latest)")
    parser.add_argument(
        "--releases-json",
        help="Optional path to a releases-array JSON file used for latest/pinned resolution",
    )
    args = parser.parse_args(argv)

    release_path = Path(args.release_json)
    release = _load_json(release_path)
    if not isinstance(release, Mapping):
        print("error: --release-json must contain a JSON object", file=sys.stderr)
        return 2

    releases: list[Mapping[str, Any]]
    if args.releases_json:
        releases_data = _load_json(Path(args.releases_json))
        if not isinstance(releases_data, list):
            print("error: --releases-json must contain a JSON array", file=sys.stderr)
            return 2
        releases = [item for item in releases_data if isinstance(item, Mapping)]
    else:
        releases = [release]

    errors: list[str] = []
    try:
        resolved_tag = resolve_release_tag(args.requested_tag, releases)
    except ValueError as exc:
        errors.append(str(exc))
        resolved_tag = ""

    actual_tag = str(release.get("tag_name", ""))
    if resolved_tag and actual_tag and resolved_tag != actual_tag:
        errors.append(f"Resolved tag {resolved_tag} does not match release tag {actual_tag}")

    errors.extend(validate_release_contract(release))

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(f"OK: release {actual_tag} passed contract validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
