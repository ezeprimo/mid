"""Tests for MarkitDownConverter and LegacyPlaceholder."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mid.converters.legacy import LegacyPlaceholder
from mid.converters.markitdown import MarkitDownConverter


# ===========================================================================
# MarkitDownConverter
# ===========================================================================


class TestMarkitDownConverter:
    def test_success_returns_content(self, tmp_path: Path) -> None:
        """MarkItDown returns text_content → ConvertResult with success."""
        src = tmp_path / "test.docx"
        src.write_text("fake", encoding="utf-8")

        with patch("markitdown.MarkItDown") as MockMD:
            instance = MockMD.return_value
            instance.convert.return_value.text_content = "# Hello Markdown"

            converter = MarkitDownConverter()
            result = converter.convert(src)

        assert result.success is True
        assert result.content == "# Hello Markdown"
        assert result.error is None
        assert result.metadata["format"] == "docx"
        assert result.metadata["source"] == "test.docx"

    def test_file_not_found(self) -> None:
        """Non-existent file returns ConvertResult with error."""
        converter = MarkitDownConverter()
        result = converter.convert(Path("no-such-file.docx"))

        assert result.success is False
        assert "not found" in (result.error or "").lower()

    def test_markitdown_raises_exception(self, tmp_path: Path) -> None:
        """MarkItDown internal error → ConvertResult with success=False."""
        src = tmp_path / "corrupt.docx"
        src.write_text("garbage", encoding="utf-8")

        with patch("markitdown.MarkItDown") as MockMD:
            instance = MockMD.return_value
            instance.convert.side_effect = RuntimeError("invalid document")

            converter = MarkitDownConverter()
            result = converter.convert(src)

        assert result.success is False
        assert "invalid document" in (result.error or "")

    def test_supported_extensions_classvar(self) -> None:
        """The class var is populated and immutable."""
        exts = MarkitDownConverter.supported_extensions
        assert ".docx" in exts
        assert ".pdf" in exts
        assert isinstance(exts, frozenset)

    def test_convert_empty_document(self, tmp_path: Path) -> None:
        """Empty content from MarkItDown still returns success."""
        src = tmp_path / "empty.docx"
        src.write_text("", encoding="utf-8")

        with patch("markitdown.MarkItDown") as MockMD:
            instance = MockMD.return_value
            instance.convert.return_value.text_content = ""

            converter = MarkitDownConverter()
            result = converter.convert(src)

        assert result.success is True
        assert result.content == ""


# ===========================================================================
# LegacyPlaceholder
# ===========================================================================


class TestLegacyPlaceholder:
    @pytest.mark.parametrize(
        "ext,modern",
        [
            (".doc", ".docx"),
            (".xls", ".xlsx"),
            (".ppt", ".pptx"),
        ],
    )
    def test_legacy_formats_return_error(
        self,
        tmp_path: Path,
        ext: str,
        modern: str,
    ) -> None:
        """All three legacy formats return success=False with helpful msg."""
        src = tmp_path / f"legacy{ext}"
        src.write_text("fake", encoding="utf-8")

        converter = LegacyPlaceholder()
        result = converter.convert(src)

        assert result.success is False
        assert result.content == ""
        assert ext in (result.error or "")
        assert modern in (result.error or "")
        assert "legacy" in (result.error or "").lower()

    def test_supported_extensions_classvar(self) -> None:
        exts = LegacyPlaceholder.supported_extensions
        assert ".doc" in exts
        assert ".xls" in exts
        assert ".ppt" in exts
        assert isinstance(exts, frozenset)

    def test_unknown_extension_still_works(self, tmp_path: Path) -> None:
        """LegacyPlaceholder ignores the file content — it just returns error."""
        src = tmp_path / "whatever.doc"
        src.write_text("anything", encoding="utf-8")

        converter = LegacyPlaceholder()
        result = converter.convert(src)

        assert result.success is False


# ===========================================================================
# Base class
# ===========================================================================


def test_converter_is_abstract() -> None:
    """Converter ABC cannot be instantiated directly."""
    from mid.converters.base import Converter

    with pytest.raises(TypeError):
        Converter()  # type: ignore[abstract]
