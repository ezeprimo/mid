"""BackendAdapter — wraps Backend as Converter with never-raise."""

from __future__ import annotations

from pathlib import Path

from mid.converters.base import Converter
from mid.models import ConvertResult
from mid.backends.base import Backend


class BackendAdapter(Converter):
    supported_extensions: frozenset[str] = frozenset()

    def __init__(self, backend: Backend) -> None:
        self.backend = backend
        # expose supported extensions for registry compatibility
        self.supported_extensions = backend.supported_extensions  # type: ignore

    def convert(self, path: Path) -> ConvertResult:
        try:
            return self.backend.convert(path)
        except Exception as exc:
            return ConvertResult(content="", metadata={}, success=False, error=str(exc))
