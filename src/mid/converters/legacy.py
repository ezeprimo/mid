"""Placeholder converter for legacy binary formats (.doc, .xls, .ppt).

These formats are not supported by MarkItDown. The converter returns a
helpful error message pointing the user to convert to the modern OOXML
equivalent first.
"""

from pathlib import Path
from typing import ClassVar

from mid.converters.base import Converter
from mid.models import ConvertResult


_LEGACY_MSG = (
    "legacy format. Convert to .docx (or .xlsx / .pptx) first "
    "using Microsoft Word (Excel / PowerPoint) or LibreOffice"
)


class LegacyPlaceholder(Converter):
    """Returns an instructive error for legacy binary formats.

    Supported extensions:
        .doc, .xls, .ppt
    """

    supported_extensions: ClassVar[frozenset[str]] = frozenset({
        ".doc", ".xls", ".ppt",
    })

    def convert(self, path: Path) -> ConvertResult:
        """Return a ``ConvertResult`` with a helpful legacy-format error.

        Args:
            path: Path to the legacy file (not actually read).

        Returns:
            A ``ConvertResult`` with ``success=False`` and an
            instructive error message.
        """
        ext = path.suffix.lower()
        modern = {".doc": ".docx", ".xls": ".xlsx", ".ppt": ".pptx"}
        modern_ext = modern.get(ext, ".docx")

        return ConvertResult(
            content="",
            metadata={},
            success=False,
            error=(
                f"{ext} is a legacy format. "
                f"Convert to {modern_ext} first using "
                "Microsoft Word, Excel, PowerPoint, or LibreOffice"
            ),
        )
