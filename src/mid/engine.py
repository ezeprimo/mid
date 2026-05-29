"""Conversion engine — registry, resolution, and orchestration."""

from pathlib import Path
from typing import Final

from mid.converters import Converter, LegacyPlaceholder, MarkitDownConverter
from mid.models import ConvertResult

# ---------------------------------------------------------------------------
# Registry: maps file extension → converter *class* (not instance).
# Add new converters here without touching any other file.
# ---------------------------------------------------------------------------

REGISTRY: Final[dict[str, type[Converter]]] = {
    ".docx": MarkitDownConverter,
    ".xlsx": MarkitDownConverter,
    ".pptx": MarkitDownConverter,
    ".pdf": MarkitDownConverter,
    ".doc": LegacyPlaceholder,
    ".xls": LegacyPlaceholder,
    ".ppt": LegacyPlaceholder,
}


def resolve_converter(ext: str) -> type[Converter] | None:
    """Look up the converter *class* for a file extension.

    Args:
        ext: File extension such as ``".docx"`` or ``".pdf"``.
             A leading dot is optional.

    Returns:
        The matching ``Converter`` subclass, or ``None`` when the
        extension is not registered.
    """
    ext = ext.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    return REGISTRY.get(ext)


def convert_file(path: Path) -> ConvertResult:
    """Convert a single file to Markdown.

    This is a convenience wrapper around ``resolve_converter`` +
    ``converter.convert()``.  Use it when you only need the result
    and don't care about the specific converter class.

    Args:
        path: Path to the file to convert.

    Returns:
        A ``ConvertResult`` — check ``.success`` to determine outcome.
    """
    ext = path.suffix.lower()
    converter_cls = resolve_converter(ext)

    if converter_cls is None:
        return ConvertResult(
            content="",
            metadata={},
            success=False,
            error=f"unsupported format {ext}",
        )

    converter = converter_cls()
    return converter.convert(path)
