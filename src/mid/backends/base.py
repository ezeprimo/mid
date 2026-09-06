"""Backend ABC and Availability dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from mid.models import ConvertResult


@dataclass(frozen=True)
class Availability:
    available: bool
    version: str | None
    tool_path: str | None
    reason: str | None
    checked_at: datetime | None


class Backend(ABC):
    """Abstract base for legacy backends."""

    name: str
    display_name: str
    supported_extensions: ClassVar[frozenset[str]] = frozenset()
    required_tools: ClassVar[tuple[str, ...]] = ()
    opt_in: bool = False

    def __init__(self) -> None:
        self._cached: Availability | None = None

    @abstractmethod
    def probe(self) -> Availability:
        """Probe backend availability. MUST never raise — return Availability."""
        ...

    @abstractmethod
    def convert(self, path: Path) -> ConvertResult:
        """Convert file, return ConvertResult."""
        ...

    def is_available(self, refresh: bool = False) -> Availability:
        # opt-in gate: until probed, return unavailable
        if self.opt_in and self._cached is None and not refresh:
            return Availability(
                available=False,
                version=None,
                tool_path=None,
                reason="detection is opt-in; run probe",
                checked_at=None,
            )
        if self._cached is not None and not refresh:
            return self._cached
        try:
            avail = self.probe()
        except Exception as exc:  # never-raise
            avail = Availability(
                available=False,
                version=None,
                tool_path=None,
                reason=str(exc) or "probe failed",
                checked_at=datetime.now(timezone.utc),
            )
        # Resilience fix (R4-001): do not cache transient failures forever — allow retry.
        # Only cache available=True; unavailable results are returned without caching
        # so a fleeting failure (TimeoutExpired, ENOSPC, fleeting PATH) is retried.
        if avail.available:
            self._cached = avail
        else:
            # Do not cache failures — clear any prior failure cache to force re-probe
            self._cached = None
        return avail
