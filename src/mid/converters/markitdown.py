"""Converter that delegates to Microsoft MarkItDown."""

from pathlib import Path
from typing import ClassVar

from mid.converters.base import Converter
from mid.models import ConvertResult


def _markdown_table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_markdown_table_separator(line: str) -> bool:
    cells = _markdown_table_cells(line)
    return bool(cells) and all(cell and set(cell) <= {":", "-"} for cell in cells)


def _is_placeholder_header_cell(cell: str) -> bool:
    normalized = cell.strip().lower()
    return not normalized or normalized == "nan" or normalized.startswith("unnamed:")


def _looks_like_placeholder_header(line: str) -> bool:
    cells = _markdown_table_cells(line)
    if not cells:
        return False
    placeholders = sum(1 for cell in cells if _is_placeholder_header_cell(cell))
    placeholder_ratio = placeholders / len(cells)
    return placeholder_ratio > 0.8 or (len(cells) > 2 and placeholders == len(cells) - 1)


def _markdown_separator_for(header_line: str) -> str:
    column_count = len(_markdown_table_cells(header_line))
    return "| " + " | ".join("---" for _ in range(column_count)) + " |"


def _promote_excel_markdown_header(content: str) -> str:
    lines = content.splitlines()
    for index in range(len(lines) - 2):
        if not (
            lines[index].lstrip().startswith("|")
            and _is_markdown_table_separator(lines[index + 1])
            and lines[index + 2].lstrip().startswith("|")
        ):
            continue
        if not _looks_like_placeholder_header(lines[index]):
            continue

        promoted_header = lines[index + 2]
        if _looks_like_placeholder_header(promoted_header):
            continue

        lines[index] = promoted_header
        lines[index + 1] = _markdown_separator_for(promoted_header)
        del lines[index + 2]
        break
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


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
            if path.suffix.lower() in {".xlsx", ".xlsm"}:
                content = _promote_excel_markdown_header(content)

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
