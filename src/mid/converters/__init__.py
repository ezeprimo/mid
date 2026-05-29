"""Converter registry — re-exports for convenience."""

from mid.converters.base import Converter
from mid.converters.legacy import LegacyPlaceholder
from mid.converters.markitdown import MarkitDownConverter

__all__ = [
    "Converter",
    "LegacyPlaceholder",
    "MarkitDownConverter",
]
