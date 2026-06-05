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


# ===========================================================================
# _clean_unnamed_headers
# ===========================================================================


class TestCleanUnnamedHeaders:
    """Unit tests for the ``_clean_unnamed_headers`` post-processing method."""

    def test_unnamed_header_is_cleaned(self) -> None:
        """A table with 'Unnamed:' in the header row is cleaned."""
        converter = MarkitDownConverter()
        raw = "## Data\n| Title | Unnamed: 1 | Unnamed: 2 |\n| --- | --- | --- |\n| RealA | RealB | RealC |\n| Data1 | Data2 | Data3 |\n"
        result = converter._clean_unnamed_headers(raw)
        assert "Unnamed:" not in result
        # Promoted row becomes header
        lines = result.strip().split("\n")
        assert "RealA" in lines[1]
        assert "RealB" in lines[1]
        # Separator row is regenerated
        assert "---" in lines[2]

    def test_no_unnamed_returns_as_is(self) -> None:
        """A table without 'Unnamed:' is left unchanged."""
        converter = MarkitDownConverter()
        raw = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        assert converter._clean_unnamed_headers(raw) == raw

    def test_no_table_returns_as_is(self) -> None:
        """Content without a Markdown table is left unchanged."""
        converter = MarkitDownConverter()
        raw = "Just some text\n\nNo table here\n"
        assert converter._clean_unnamed_headers(raw) == raw

    def test_all_rows_unnamed_returns_as_is(self) -> None:
        """When every row contains 'Unnamed:', nothing is promoted."""
        converter = MarkitDownConverter()
        raw = "| Unnamed: 0 | Unnamed: 1 |\n| --- | --- |\n| Unnamed: 2 | Unnamed: 3 |\n"
        assert converter._clean_unnamed_headers(raw) == raw

    def test_nan_header_is_cleaned(self) -> None:
        """A header row containing 'NaN' is also cleaned."""
        converter = MarkitDownConverter()
        raw = "| NaN | NaN |\n| --- | --- |\n| H1 | H2 |\n| V1 | V2 |\n"
        result = converter._clean_unnamed_headers(raw)
        lines = [l for l in result.split("\n") if l.strip()]
        assert "NaN" not in lines[0]  # header line
        assert "H1" in lines[0]

    def test_single_data_row(self) -> None:
        """A table with exactly one data row is still handled."""
        converter = MarkitDownConverter()
        raw = "| U | Unnamed: 1 |\n| --- | --- |\n| Ok | Data |\n"
        result = converter._clean_unnamed_headers(raw)
        lines = [l for l in result.split("\n") if l.strip()]
        assert "Unnamed:" not in result
        assert "Ok" in lines[0]  # promoted header is first non-empty line

    def test_multiple_tables_only_first_cleaned(self) -> None:
        """Only the first table with 'Unnamed:' is processed; later tables untouched."""
        converter = MarkitDownConverter()
        raw = "| Bad | Unnamed: 1 |\n| --- | --- |\n| Good | Data |\n\n## Section\n| Normal | Table |\n| --- | --- |\n| x | y |\n"
        result = converter._clean_unnamed_headers(raw)
        assert "Unnamed:" not in result
        assert "Normal" in result
        assert "Table" in result

    def test_separator_column_count_matches_promoted_header(self) -> None:
        """The generated separator has the same column count as the promoted header."""
        converter = MarkitDownConverter()
        raw = "| A | B | C | D | Unnamed: 5 |\n| --- | --- | --- | --- | --- |\n| W | X | Y | Z | Last |\n"
        result = converter._clean_unnamed_headers(raw)
        sep_line = [l for l in result.split("\n") if "---" in l and l.strip().startswith("|")][0]
        assert sep_line.count("---") == 5


# ===========================================================================
# _strip_toc_text
# ===========================================================================


class TestStripTocText:
    """Unit tests for the ``_strip_toc_text`` post-processing method."""

    def test_strips_toc_before_first_heading(self) -> None:
        """TOC-like lines before the first heading are stripped."""
        converter = MarkitDownConverter()
        raw = "1. Introduction 3\n1.1 Objective 3\n1.2 Audience 4\n\n# 1. Introduction\n\nContent here.\n"
        result = converter._strip_toc_text(raw)
        assert "Introduction 3" not in result.split("\n")[0]
        assert "# 1. Introduction" in result

    def test_no_toc_returns_as_is(self) -> None:
        """Content without TOC pattern is left unchanged."""
        converter = MarkitDownConverter()
        raw = "# Just a heading\n\nSome text\n"
        assert converter._strip_toc_text(raw) == raw

    def test_empty_content_returns_as_is(self) -> None:
        """Empty string is returned unchanged."""
        converter = MarkitDownConverter()
        assert converter._strip_toc_text("") == ""

    def test_toc_like_after_heading_is_preserved(self) -> None:
        """Lines matching the TOC pattern but after a heading are NOT removed."""
        converter = MarkitDownConverter()
        raw = "# Real heading\n\n1. Not TOC (no page number)\n"
        assert converter._strip_toc_text(raw) == raw

    def test_heading_as_first_line_returns_as_is(self) -> None:
        """When heading is the very first line, no TOC stripping occurs."""
        converter = MarkitDownConverter()
        raw = "# Top heading\n\ncontent\n"
        assert converter._strip_toc_text(raw) == raw

    def test_blank_lines_between_toc_and_heading(self) -> None:
        """Blank lines between TOC block and heading are tolerated."""
        converter = MarkitDownConverter()
        raw = "1. Intro 3\n1.1 Sub 4\n\n\n# Intro\n\nbody\n"
        result = converter._strip_toc_text(raw)
        assert "Intro 3" not in result
        assert "# Intro" in result

    def test_mixed_content_before_toc_is_preserved(self) -> None:
        """Non-TOC content before the TOC block is preserved."""
        converter = MarkitDownConverter()
        raw = "Some preamble text.\n\n1. Chapter 1 10\n\n# Chapter 1\n\nbody\n"
        result = converter._strip_toc_text(raw)
        assert "Some preamble text" in result
        assert "Chapter 1 10" not in result


# ===========================================================================
# _cleanup orchestrator
# ===========================================================================


class TestCleanup:
    """Tests for ``_cleanup`` which runs both post-processing steps in order."""

    def test_toc_and_unnamed_are_both_applied(self) -> None:
        """_cleanup applies TOC stripping first, then unnamed header cleaning."""
        converter = MarkitDownConverter()
        raw = "1. TOC Entry 3\n\n# Data\n| Bad | Unnamed: 1 |\n| --- | --- |\n| H1 | H2 |\n| V1 | V2 |\n"
        result = converter._cleanup(raw)
        lines = [l for l in result.split("\n") if l.strip()]
        # TOC stripped
        assert "TOC Entry 3" not in result
        # Unnamed header cleaned
        assert "Unnamed:" not in result
        # Actual header promoted (should be right after # Data)
        promo_idx = next(i for i, l in enumerate(lines) if "H1" in l)
        data_idx = next(i for i, l in enumerate(lines) if "# Data" in l)
        assert promo_idx == data_idx + 1  # promoted header follows # Data

    def test_cleanup_empty_content(self) -> None:
        """_cleanup on empty content returns empty."""
        converter = MarkitDownConverter()
        assert converter._cleanup("") == ""

    def test_cleanup_no_issues_returns_as_is(self) -> None:
        """_cleanup with clean content returns unchanged."""
        converter = MarkitDownConverter()
        raw = "# Hello\n\nNormal content.\n"
        assert converter._cleanup(raw) == raw


# ===========================================================================
# ffmpeg warning suppression
# ===========================================================================


class TestFfmpegWarningSuppression:
    """Verify that the ffmpeg/pydub RuntimeWarning is suppressed during convert()."""

    def test_no_ffmpeg_warning_in_convert_stderr(self, tmp_path: Path) -> None:
        """Running convert() on a .docx produces zero ffmpeg warnings on stderr."""
        import io
        import sys

        src = tmp_path / "test.docx"
        src.write_text("fake", encoding="utf-8")

        converter = MarkitDownConverter()
        stderr_capture = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = stderr_capture

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = "# Works"

            converter.convert(src)

        sys.stderr = old_stderr
        stderr_output = stderr_capture.getvalue()
        assert "ffmpeg" not in stderr_output.lower()


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
