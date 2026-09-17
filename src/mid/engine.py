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


def get_backend(name: str):
    """Return backend by name or None (facade over registry)."""
    from mid.backends.registry import registry

    return registry.get(name)


def list_backends():
    """Return all registered backends in insertion order."""
    from mid.backends.registry import registry

    return registry.list_all()


def resolve_backend(ext: str, preferred: str | None = None):
    """Resolve backend for extension. Returns None on ambiguity or unknown."""
    from mid.backends.registry import registry

    ext = ext.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    candidates = [b for b in registry.list_all() if ext in b.supported_extensions]
    if not candidates:
        return None
    if preferred is not None:
        for b in candidates:
            if b.name == preferred:
                return b
        return None
    if len(candidates) == 1:
        return candidates[0]
    return None


def convert_file(path: Path, *, backend: str | None = None) -> ConvertResult:
    """Convert a single file to Markdown.

    This is a convenience wrapper around ``resolve_converter`` +
    ``converter.convert()``.  Use it when you only need the result
    and don't care about the specific converter class.

    Args:
        path: Path to the file to convert.
        backend: Optional backend name. When set, delegates to that backend.

    Returns:
        A ``ConvertResult`` — check ``.success`` to determine outcome.
    """
    if backend is not None:
        from mid.backends.registry import registry

        b = registry.get(backend)
        if b is None:
            available = ", ".join([x.name for x in registry.list_all()]) or "none"
            return ConvertResult(
                content="",
                metadata={},
                success=False,
                error=f"unknown backend '{backend}'; available: {available}",
            )
        try:
            # Explicit backend= selection is consent to probe, including opt-in backends.
            avail = b.is_available(refresh=True)
        except Exception as exc:  # never-raise
            return ConvertResult(content="", metadata={}, success=False, error=str(exc))
        if not avail.available:
            reason = avail.reason or "unavailable"
            return ConvertResult(content="", metadata={}, success=False, error=reason)
        try:
            return b.convert(path)
        except Exception as exc:
            return ConvertResult(content="", metadata={}, success=False, error=str(exc))

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
