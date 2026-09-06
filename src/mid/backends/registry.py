"""BackendRegistry — explicit deterministic insertion-order registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mid.backends.base import Backend


class BackendRegistry:
    def __init__(self) -> None:
        self._backends: dict[str, Backend] = {}

    def register(self, backend: Backend) -> None:
        name = backend.name
        if name in self._backends:
            existing = self._backends[name]
            if existing is backend:
                return
            raise ValueError(f"backend '{name}' already registered")
        self._backends[name] = backend

    def get(self, name: str) -> Backend | None:
        return self._backends.get(name)

    def list_all(self) -> list[Backend]:
        return list(self._backends.values())

    def available_backends(self) -> list[Backend]:
        return [b for b in self._backends.values() if b.is_available().available]

    def clear(self) -> None:
        self._backends.clear()


# Global singleton
registry = BackendRegistry()
