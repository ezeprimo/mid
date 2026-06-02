"""Tests for mid.engine — converter resolution and conversion orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mid.engine import convert_file, resolve_converter
from mid.converters.legacy import LegacyPlaceholder
from mid.converters.markitdown import MarkitDownConverter


class TestResolveConverter:
    @pytest.mark.parametrize(
        ("ext", "expected"),
        [
            (".docx", MarkitDownConverter),
            ("docx", MarkitDownConverter),
            (".DOCX", MarkitDownConverter),
            (".xlsx", MarkitDownConverter),
            (".pptx", MarkitDownConverter),
            (".pdf", MarkitDownConverter),
            (".doc", LegacyPlaceholder),
            (".xls", LegacyPlaceholder),
            (".ppt", LegacyPlaceholder),
        ],
    )
    def test_known_extensions(self, ext: str, expected) -> None:
        assert resolve_converter(ext) is expected

    @pytest.mark.parametrize(
        ("ext",),
        [
            (".xyz",),
            (".tar.gz",),
            (".",),
            ("",),
            ("unknown",),
        ],
    )
    def test_unknown_extensions(self, ext: str) -> None:
        assert resolve_converter(ext) is None


class TestConvertFile:
    def test_supported_extension(self, tmp_path: Path) -> None:
        src = tmp_path / "test.docx"
        src.write_text("fake", encoding="utf-8")

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = "# Engine test"

            result = convert_file(src)

        assert result.success is True
        assert result.content == "# Engine test"

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        src = tmp_path / "test.xyz"
        src.write_text("fake", encoding="utf-8")

        result = convert_file(src)

        assert result.success is False
        assert "unsupported format" in (result.error or "").lower()

    def test_non_existent_file(self) -> None:
        """Non-existent file is handled gracefully via mock."""
        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.side_effect = FileNotFoundError("no such file")
            result = convert_file(Path("no-such-file.docx"))

        assert result.success is False
        assert "not found" in (result.error or "").lower()
