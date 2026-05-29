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
    """

    content: str
    metadata: dict
    success: bool
    error: str | None
