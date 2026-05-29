"""Abstract base class for document converters."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from mid.models import ConvertResult


class Converter(ABC):
    """Abstract base for all document converters.

    Each converter declares which file extensions it supports via
    ``supported_extensions`` and implements ``convert()`` to produce
    a ``ConvertResult``.

    Converters **never raise exceptions** – all errors are captured
    inside the returned ``ConvertResult`` with ``success=False``.
    """

    supported_extensions: ClassVar[frozenset[str]]

    @abstractmethod
    def convert(self, path: Path) -> ConvertResult:
        """Convert *path* to Markdown.

        Args:
            path: Absolute or relative path to the source file.

        Returns:
            A ``ConvertResult`` carrying the markdown content on success
            or an error description on failure.
        """
        ...
