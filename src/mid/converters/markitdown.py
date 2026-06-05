"""Converter that delegates to Microsoft MarkItDown."""

import re
import warnings
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

    def _clean_unnamed_headers(self, content: str) -> str:
        """Detect and clean 'Unnamed:' / 'NaN' headers in the first Markdown table.

        If the header row (first row) contains any cell with 'Unnamed:' or 'NaN',
        drop the header row AND the separator row, then promote the first data
        row to become the new header.

        Edge cases:
        - No table found            → return content unchanged
        - No 'Unnamed:' cells       → return content unchanged
        - First data row ALSO has
          'Unnamed:' cells          → return content unchanged
        - Multiple tables           → only process the first one
        """
        lines = content.split("\n")

        # --- locate the first table -------------------------------------------
        table_start = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                table_start = i
                break

        if table_start < 0:
            return content  # no table at all

        # find end of the table (blank line or end of content)
        table_end = len(lines)
        for i in range(table_start + 1, len(lines)):
            if not lines[i].strip():
                table_end = i
                break

        # need at least header + separator + one data row
        if table_end - table_start < 3:
            return content

        header_idx = table_start
        first_data_idx = table_start + 2

        # --- check the header row ---------------------------------------------
        header_cells = [
            c.strip() for c in lines[header_idx].strip().strip("|").split("|")
        ]
        if not any("Unnamed:" in c or c == "NaN" for c in header_cells):
            return content  # nothing to clean

        # --- check first data row (all-unnamed guard) -------------------------
        first_data_cells = [
            c.strip() for c in lines[first_data_idx].strip().strip("|").split("|")
        ]
        if any("Unnamed:" in c or c == "NaN" for c in first_data_cells):
            return content  # nothing to promote

        # --- promote first data row to header ---------------------------------
        # count columns from the promoted row to generate a proper separator
        num_cols = len(first_data_cells)
        sep_row = "|" + "---|" * num_cols

        new_lines = lines[:table_start]                 # lines before the table
        new_lines.append(lines[first_data_idx])         # promoted header
        new_lines.append(sep_row)                       # generated separator
        new_lines.extend(lines[first_data_idx + 1:table_end])  # remaining data
        new_lines.extend(lines[table_end:])             # lines after the table

        return "\n".join(new_lines)

    def _strip_toc_text(self, content: str) -> str:
        r"""Remove TOC field lines that appear before the first ``#`` heading.

        Strips lines matching ``^\d+(\.\d+)*\.?\s+.*\s+\d+$`` (e.g.
        ``1. Introduction 3``) when they form a contiguous block before the
        first heading marker.

        Edge cases:
        - Empty content                  → return as-is
        - No TOC pattern                 → return as-is
        - Matching lines AFTER heading   → NOT touched
        """
        lines = content.split("\n")

        # --- locate the first heading -----------------------------------------
        first_heading = -1
        for i, line in enumerate(lines):
            if re.match(r"^#", line.strip()):
                first_heading = i
                break

        if first_heading <= 0:
            return content  # no heading, or heading is the very first line

        # --- walk backwards from heading to find contiguous TOC block ----------
        toc_pattern = re.compile(r"^\d+(\.\d+)*\.?\s+.*\s+\d+$")
        toc_start = first_heading
        toc_end = first_heading

        for i in range(first_heading - 1, -1, -1):
            stripped = lines[i].strip()
            if not stripped:
                continue  # blank lines between TOC and heading are OK
            if toc_pattern.match(stripped):
                toc_start = i
            else:
                break

        if toc_start >= toc_end:
            return content  # no contiguous TOC block found

        # remove only the TOC-pattern lines (blank lines between TOC and heading
        # are left in place so the content structure is preserved)
        cleaned = lines[:toc_start]
        for i in range(toc_start, toc_end):
            if not toc_pattern.match(lines[i].strip()):
                cleaned.append(lines[i])
        cleaned.extend(lines[toc_end:])
        return "\n".join(cleaned)

    def _cleanup(self, content: str) -> str:
        """Apply all post-processing steps in order."""
        content = self._strip_toc_text(content)
        content = self._clean_unnamed_headers(content)
        return content

    def convert(self, path: Path) -> ConvertResult:
        """Convert *path* via MarkItDown.

        Returns:
            A ``ConvertResult`` with the markdown content on success
            or an error description on failure.
        """
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*ffmpeg.*")
                from markitdown import MarkItDown

            md = MarkItDown()
            result = md.convert(str(path))
            content = self._cleanup(result.text_content) if result else ""

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
