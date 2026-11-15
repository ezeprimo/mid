"""Data models for mid."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConvertResult:
    """Result of a document conversion.

    Attributes:
        content: The converted Markdown content.
        metadata: Dictionary with conversion metadata (source, format, success).
        success: Whether the conversion succeeded.
        error: Error message if conversion failed, None otherwise.
        exit_code: Optional exit code a backend assigns to this failure (e.g. 3
            for a safety abort). ``None`` means "use the CLI default", which is
            exit 1 for a conversion error.
    """

    content: str
    metadata: dict
    success: bool
    error: str | None
    exit_code: int | None = None
