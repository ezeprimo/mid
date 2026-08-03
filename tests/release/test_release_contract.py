from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.release.validate_release import (
    main,
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


def _make_valid_release(tag: str = "v1.2.3") -> dict:
    version = tag[1:] if tag.startswith("v") else tag
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": "mid-windows-amd64.exe"},
            {"name": "mid-linux-amd64"},
            {"name": "checksums.txt"},
            {"name": f"mid-{version}-py3-none-any.whl"},
            {"name": f"mid-{version}.tar.gz"},
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
                f"MID_VERSION={tag}",
                "## Fallback",
                f"pipx install mid=={version}",
                "## Rollback",
                "Rollback by reinstalling an older version",
            ]
        ),
    }


class TestValidateReleaseMain:
    def test_valid_release_exits_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        release = _make_valid_release("v1.2.3")
        path = tmp_path / "release.json"
        path.write_text(json.dumps(release), encoding="utf-8")

        rc = main(["--release-json", str(path)])

        assert rc == 0
        assert "OK: release v1.2.3 passed contract validation" in capsys.readouterr().err

    def test_release_json_is_array_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "array.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        rc = main(["--release-json", str(path)])

        assert rc == 2
        assert "--release-json must contain a JSON object" in capsys.readouterr().err

    def test_missing_release_json_exits_2(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main([])

        assert excinfo.value.code == 2

    def test_requested_tag_not_resolved_exits_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        release = _make_valid_release("v1.2.3")
        path = tmp_path / "release.json"
        path.write_text(json.dumps(release), encoding="utf-8")

        rc = main(["--release-json", str(path), "--requested-tag", "v9.9.9"])

        assert rc == 1
        assert "ERROR:" in capsys.readouterr().err

    def test_releases_json_not_array_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        release = _make_valid_release("v1.2.3")
        valid = tmp_path / "release.json"
        valid.write_text(json.dumps(release), encoding="utf-8")
        obj = tmp_path / "releases.json"
        obj.write_text(json.dumps({"not": "an array"}), encoding="utf-8")

        rc = main(["--release-json", str(valid), "--releases-json", str(obj)])

        assert rc == 2
        assert "--releases-json must contain a JSON array" in capsys.readouterr().err

    def test_invalid_contract_exits_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        release = _make_valid_release("v1.2.3")
        release["assets"] = [
            asset for asset in release["assets"] if asset["name"] != "mid-linux-amd64"
        ]
        path = tmp_path / "release.json"
        path.write_text(json.dumps(release), encoding="utf-8")

        rc = main(["--release-json", str(path)])

        assert rc == 1
        err = capsys.readouterr().err
        assert "ERROR:" in err
        assert "Missing required asset" in err

    def test_pinned_tag_resolves_when_in_releases(self, tmp_path: Path) -> None:
        v123 = _make_valid_release("v1.2.3")
        v110 = _make_valid_release("v1.1.0")
        v100 = _make_valid_release("v1.0.0")
        valid_v123 = tmp_path / "release.json"
        valid_v123.write_text(json.dumps(v123), encoding="utf-8")
        releases = tmp_path / "releases.json"
        releases.write_text(json.dumps([v100, v110, v123]), encoding="utf-8")

        rc = main(
            [
                "--release-json",
                str(valid_v123),
                "--requested-tag",
                "v1.2.3",
                "--releases-json",
                str(releases),
            ]
        )

        assert rc == 0

    def test_latest_skips_draft_and_prerelease(self, tmp_path: Path) -> None:
        v100 = _make_valid_release("v1.0.0")
        v200_draft = _make_valid_release("v2.0.0")
        v200_draft["draft"] = True
        v300_pre = _make_valid_release("v3.0.0")
        v300_pre["prerelease"] = True
        valid_v100 = tmp_path / "release.json"
        valid_v100.write_text(json.dumps(v100), encoding="utf-8")
        releases = tmp_path / "releases.json"
        releases.write_text(json.dumps([v100, v200_draft, v300_pre]), encoding="utf-8")

        rc = main(
            [
                "--release-json",
                str(valid_v100),
                "--requested-tag",
                "latest",
                "--releases-json",
                str(releases),
            ]
        )

        assert rc == 0
