from __future__ import annotations

import pytest

from scripts.release.render_release_notes import main, normalize_version, render_release_notes
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


class TestRenderReleaseNotesMain:
    FULL_ARGS = ["--version", "v1.2.3", "--repo", "owner/name"]
    EXPECTED_SECTIONS = (
        "## Install Windows",
        "## Install Linux",
        "## Version Pinning",
        "## Fallback (pipx/pip)",
        "## Rollback",
        "## Uninstall",
    )

    def test_writes_markdown_with_required_sections(self, tmp_path) -> None:
        notes = tmp_path / "notes.md"

        exit_code = main([*self.FULL_ARGS, "--output", str(notes)])

        assert exit_code == 0
        assert notes.exists()
        content = notes.read_text(encoding="utf-8")
        assert "# mid v1.2.3" in content
        for section in self.EXPECTED_SECTIONS:
            assert section in content

    def test_version_without_v_prefix_is_normalized(self, tmp_path) -> None:
        notes = tmp_path / "notes.md"

        exit_code = main(["--version", "1.2.3", "--repo", "owner/name", "--output", str(notes)])

        assert exit_code == 0
        assert "# mid v1.2.3" in notes.read_text(encoding="utf-8")

    def test_creates_missing_parent_directories(self, tmp_path) -> None:
        notes = tmp_path / "deep" / "nested" / "notes.md"
        assert not notes.parent.exists()

        exit_code = main([*self.FULL_ARGS, "--output", str(notes)])

        assert exit_code == 0
        assert notes.parent.exists()
        assert notes.exists()

    @pytest.mark.parametrize(
        "missing_flag, argv",
        [
            ("--version", ["--repo", "owner/name", "--output", "notes.md"]),
            ("--repo", ["--version", "v1.2.3", "--output", "notes.md"]),
            ("--output", ["--version", "v1.2.3", "--repo", "owner/name"]),
        ],
    )
    def test_missing_required_argument_exits_2(self, missing_flag, argv, capsys) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(argv)

        assert exc_info.value.code == 2
        stderr = capsys.readouterr().err
        assert missing_flag in stderr
