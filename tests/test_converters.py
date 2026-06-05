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
        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.side_effect = FileNotFoundError("no such file")
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

    def test_markitdown_returns_none(self, tmp_path: Path) -> None:
        """If MarkItDown returns None, the result guard handles it gracefully."""
        src = tmp_path / "test.docx"
        src.write_text("", encoding="utf-8")

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value = None

            converter = MarkitDownConverter()
            result = converter.convert(src)

        assert result.success is True
        assert result.content == ""

    def test_markitdown_result_missing_text_content(self, tmp_path: Path) -> None:
        """If the result is truthy but has no text_content, it's caught gracefully."""
        src = tmp_path / "test.docx"
        src.write_text("", encoding="utf-8")

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            # Return a truthy object without text_content
            inst.convert.return_value = object()

            converter = MarkitDownConverter()
            result = converter.convert(src)

        assert result.success is False
        assert result.error is not None

    def test_excel_merged_header_rows_are_promoted(self, tmp_path: Path) -> None:
        """Excel output with placeholder headers promotes the next row as the table header."""
        src = tmp_path / "merged.xlsx"
        src.write_text("", encoding="utf-8")
        markdown = (
            "| Report Title | Unnamed: 1 | Unnamed: 2 |\n"
            "| --- | --- | --- |\n"
            "| Opción del menú contextual | Estado | Moneda |\n"
            "| Opción 1 | Completado | ARS |\n"
        )

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = markdown

            converter = MarkitDownConverter()
            result = converter.convert(src)

        expected = "| Opción del menú contextual | Estado | Moneda |\n| --- | --- | --- |\n| Opción 1 | Completado | ARS |\n"
        assert result.success is True
        assert result.content == expected

    def test_excel_unnamed_header_rows_are_promoted(self, tmp_path: Path) -> None:
        """Excel output with mostly placeholder cells promotes the next row."""
        src = tmp_path / "unnamed.xlsx"
        src.write_text("", encoding="utf-8")
        markdown = (
            "| Unnamed: 0 | Unnamed: 1 | Unnamed: 2 |\n"
            "| --- | --- | --- |\n"
            "| Name | Status | Currency |\n"
            "| Option 1 | Complete | ARS |\n"
        )

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = markdown

            converter = MarkitDownConverter()
            result = converter.convert(src)

        expected = "| Name | Status | Currency |\n| --- | --- | --- |\n| Option 1 | Complete | ARS |\n"
        assert result.success is True
        assert result.content == expected

    def test_excel_placeholder_rows_are_not_promoted_twice(self, tmp_path: Path) -> None:
        """Do not promote a second placeholder-like row as a table header."""
        src = tmp_path / "placeholder.xlsx"
        src.write_text("", encoding="utf-8")
        markdown = (
            "| Unnamed: 0 | Unnamed: 1 | Unnamed: 2 |\n"
            "| --- | --- | --- |\n"
            "| Report | Unnamed: 1 | Unnamed: 2 |\n"
            "| Name | Status | Currency |\n"
        )

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = markdown

            converter = MarkitDownConverter()
            result = converter.convert(src)

        assert result.success is True
        assert result.content == markdown

    def test_non_excel_placeholder_like_markdown_is_unchanged(self, tmp_path: Path) -> None:
        """Only Excel conversions receive the merged-header table cleanup."""
        src = tmp_path / "table.docx"
        src.write_text("", encoding="utf-8")
        markdown = (
            "| Report Title | Unnamed: 1 | Unnamed: 2 |\n"
            "| --- | --- | --- |\n"
            "| Opción del menú contextual | Estado | Moneda |\n"
        )

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = markdown

            converter = MarkitDownConverter()
            result = converter.convert(src)

        assert result.success is True
        assert result.content == markdown


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


# ===========================================================================
# ConvertResult immutability
# ===========================================================================


class TestConvertResult:
    def test_frozen_dataclass_rejects_mutation(self) -> None:
        """ConvertResult is frozen — mutation must raise."""
        from dataclasses import FrozenInstanceError
        from mid.models import ConvertResult

        result = ConvertResult(content="test", metadata={}, success=True, error=None)
        with pytest.raises(FrozenInstanceError):
            result.content = "changed"  # type: ignore[misc]

    def test_metadata_dict_is_mutable(self) -> None:
        """The metadata dict inside a frozen dataclass is still mutable."""
        from mid.models import ConvertResult

        result = ConvertResult(content="test", metadata={"key": "val"}, success=True, error=None)
        result.metadata["new_key"] = "new_val"  # should work despite frozen
        assert result.metadata["new_key"] == "new_val"
