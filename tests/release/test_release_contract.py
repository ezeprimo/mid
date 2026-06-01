from __future__ import annotations

import copy

import pytest

from scripts.release.validate_release import (
    resolve_release_tag,
    validate_release_contract,
)


def _stable_release_payload() -> dict:
    return {
        "tag_name": "v1.2.3",
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": "mid-windows-amd64.exe"},
            {"name": "mid-linux-amd64"},
            {"name": "mid-1.2.3-py3-none-any.whl"},
            {"name": "mid-1.2.3.tar.gz"},
            {"name": "checksums.txt"},
        ],
        "checksums_content": "\n".join(
            [
                "a" * 64 + "  mid-windows-amd64.exe",
                "b" * 64 + "  mid-linux-amd64",
            ]
        ),
        "body": "\n".join(
            [
                "## Windows",
                "irm https://example/install.ps1 | iex",
                "## Linux",
                "curl -fsSL https://example/install.sh | bash",
                "## Pinning",
                "MID_VERSION=v1.2.3",
                "## Fallback",
                "pipx install mid==1.2.3",
                "## Rollback",
                "Rollback by reinstalling with MID_VERSION=v1.2.2",
            ]
        ),
    }


def test_stable_release_with_required_assets_and_versions_passes() -> None:
    release = _stable_release_payload()
    errors = validate_release_contract(release)
    assert errors == []


def test_latest_resolves_to_newest_stable_not_prerelease() -> None:
    stable = _stable_release_payload()
    prerelease = copy.deepcopy(stable)
    prerelease["tag_name"] = "v1.3.0"
    prerelease["prerelease"] = True

    resolved = resolve_release_tag("latest", [stable, prerelease])
    assert resolved == "v1.2.3"

    pinned = resolve_release_tag("v1.2.3", [stable, prerelease])
    assert pinned == "v1.2.3"


def test_missing_linux_checksum_is_non_compliant() -> None:
    release = _stable_release_payload()
    release["checksums_content"] = "\n".join(
        [
            "a" * 64 + "  mid-windows-amd64.exe",
        ]
    )

    errors = validate_release_contract(release)

    assert errors
    assert any("Missing checksum entry for mid-linux-amd64" in msg for msg in errors)


def test_requested_tag_not_found_raises() -> None:
    stable = _stable_release_payload()
    with pytest.raises(ValueError, match="Requested release tag not found"):
        resolve_release_tag("v9.9.9", [stable])
