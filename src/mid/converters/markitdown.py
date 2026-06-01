"""Converter that delegates to Microsoft MarkItDown."""

from pathlib import Path
from typing import ClassVar

from mid.converters.base import Converter
from mid.models import ConvertResult


class MarkitDownConverter(Converter):
    """Wraps ``markitdown.MarkItDown`` to convert modern Office formats.

    Supported extensions:
        .docx, .xlsx, .pptx, .pdf, .html, .csv, .json, .xml, .epub
    """

    supported_extensions: ClassVar[frozenset[str]] = frozenset(
        {
            ".docx",
            ".xlsx",
            ".pptx",
            ".pdf",
            ".html",
            ".csv",
            ".json",
            ".xml",
            ".epub",
        }
    )

    def convert(self, path: Path) -> ConvertResult:
        """Convert *path* via MarkItDown.

        Returns:
            A ``ConvertResult`` with the markdown content on success
            or an error description on failure.
        """
        try:
            from markitdown import MarkItDown

            md = MarkItDown()
            result = md.convert(str(path))
            content = result.text_content if result else ""

            return ConvertResult(
                content=content,
                metadata={
                    "source": path.name,
                    "format": path.suffix.lstrip("."),
                    "success": True,
                },
                success=True,
                error=None,
            )
        except FileNotFoundError:
            return ConvertResult(
                content="",
                metadata={},
                success=False,
                error=f"File not found: {path.name}",
            )
        except Exception as exc:
            return ConvertResult(
                content="",
                metadata={},
                success=False,
                error=str(exc),
            )
