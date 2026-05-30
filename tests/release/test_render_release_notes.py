from __future__ import annotations

from scripts.release.render_release_notes import normalize_version, render_release_notes
from scripts.release.validate_release import validate_release_contract


def _base_release_payload(body: str) -> dict:
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
        "body": body,
    }


def test_normalize_version_accepts_tag_or_plain() -> None:
    assert normalize_version("v1.2.3") == ("v1.2.3", "1.2.3")
    assert normalize_version("1.2.3") == ("v1.2.3", "1.2.3")


def test_rendered_notes_satisfy_release_contract_requirements() -> None:
    notes = render_release_notes("v1.2.3", "1.2.3", "owner/repo")
    release = _base_release_payload(notes)

    errors = validate_release_contract(release)

    assert errors == []
