"""Conversion engine — registry, resolution, and orchestration."""

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Final

from mid.converters import Converter, LegacyPlaceholder, MarkitDownConverter
from mid.models import ConvertResult

if TYPE_CHECKING:
    # Type-only: importing ``mid.backends.base`` for real would trigger the
    # backends package ``__init__`` (and its registration side effects) at
    # engine import time, so backend modules stay lazily imported here.
    from mid.backends.base import Availability

logger = logging.getLogger(__name__)

# Private metadata key carrying this function's own stage timings. The CLI pops
# it before building a payload, so it never reaches users.
TIMINGS_KEY: Final = "_timings"

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


def backend_only_formats() -> list[str]:
    """Return extensions no native converter handles but a backend declares.

    These are the formats ``mid convert`` can reach through auto-routing. The
    list is derived, never hardcoded: a backend that stops declaring an
    extension stops advertising it.
    """
    from mid.backends.registry import registry

    advertised: set[str] = set()
    for backend in registry.list_all():
        advertised.update(backend.supported_extensions)
    return sorted(ext for ext in advertised if ext not in REGISTRY)


def resolve_backend(ext: str, preferred: str | None = None):
    """Resolve backend for extension. Returns None on ambiguity or unknown."""
    from mid.backends.registry import registry

    ext = ext.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    candidates = [b for b in registry.list_all() if ext in b.supported_extensions]
    logger.debug("backend candidates for %s: %s", ext, [b.name for b in candidates])
    if not candidates:
        logger.info("no backend supports %s", ext)
        return None
    if preferred is not None:
        for b in candidates:
            if b.name == preferred:
                logger.info("selected backend '%s' for %s", b.name, ext)
                return b
        logger.info("preferred backend '%s' does not support %s", preferred, ext)
        return None
    if len(candidates) == 1:
        logger.info("selected backend '%s' for %s", candidates[0].name, ext)
        return candidates[0]
    logger.info("ambiguous backend for %s (%d candidates)", ext, len(candidates))
    return None


def _stamp_timings(
    result: ConvertResult,
    *,
    detection_s: float,
    probe_s: float,
    conversion_s: float,
) -> ConvertResult:
    """Attach the stages measured here to *result* and return it.

    Truncation (``int``) keeps ``detection + probe + conversion <= total`` true,
    which rounding would not. Failure paths are stamped too: a failed conversion
    is exactly when the user needs to know whether the probe or the conversion
    was the slow part.
    """
    result.metadata[TIMINGS_KEY] = {
        "detection_ms": int(detection_s * 1000),
        "probe_ms": int(probe_s * 1000),
        "conversion_ms": int(conversion_s * 1000),
    }
    return result


def convert_file(
    path: Path,
    *,
    backend: str | None = None,
    availability: "Availability | None" = None,
) -> ConvertResult:
    """Convert a single file to Markdown.

    This is a convenience wrapper around ``resolve_converter`` +
    ``converter.convert()``.  Use it when you only need the result
    and don't care about the specific converter class.

    Args:
        path: Path to the file to convert.
        backend: Optional backend name. When set, delegates to that backend.
        availability: Optional already obtained ``Availability`` for
            ``backend``. A caller that had to probe anyway (the CLI gate on an
            explicit ``--backend``) passes it here so the probe is paid once
            instead of twice. It carries the fact "already proven" rather than
            a bare boolean a caller could set wrongly, and the never-raise
            contract stays in ``Backend.is_available``. When ``None`` — the
            library path — this function probes for itself exactly as before.

    Returns:
        A ``ConvertResult`` — check ``.success`` to determine outcome. Its
        ``metadata`` carries the private ``_timings`` key with the
        ``detection_ms``/``probe_ms``/``conversion_ms`` stages measured here.
        ``probe_ms`` is ``0`` when ``availability`` was supplied: nothing was
        probed here, and the caller's own measurement covers that stage.
    """
    started = time.perf_counter()

    if backend is not None:
        from mid.backends.registry import registry

        logger.info("delegating %s to backend '%s'", path.name, backend)
        b = registry.get(backend)
        detection_s = time.perf_counter() - started
        if b is None:
            available = ", ".join([x.name for x in registry.list_all()]) or "none"
            logger.info("unknown backend '%s'", backend)
            return _stamp_timings(
                ConvertResult(
                    content="",
                    metadata={},
                    success=False,
                    error=f"unknown backend '{backend}'; available: {available}",
                ),
                detection_s=detection_s,
                probe_s=0.0,
                conversion_s=0.0,
            )
        probe_started = time.perf_counter()
        if availability is not None:
            # The caller already paid for the probe (#70): probing again with
            # refresh=True would double it (two COM opens, up to 2x the probe
            # budget per file). The stage is a measured zero, not a guess.
            avail = availability
            probe_s = time.perf_counter() - probe_started
        else:
            try:
                # Explicit backend= selection is consent to probe, including opt-in backends.
                avail = b.is_available(refresh=True)
            except Exception as exc:  # never-raise
                logger.info("backend '%s' probe raised: %s", backend, exc)
                return _stamp_timings(
                    ConvertResult(content="", metadata={}, success=False, error=str(exc)),
                    detection_s=detection_s,
                    probe_s=time.perf_counter() - probe_started,
                    conversion_s=0.0,
                )
            probe_s = time.perf_counter() - probe_started
        if not avail.available:
            reason = avail.reason or "unavailable"
            logger.info("backend '%s' unavailable: %s", backend, reason)
            return _stamp_timings(
                ConvertResult(content="", metadata={}, success=False, error=reason),
                detection_s=detection_s,
                probe_s=probe_s,
                conversion_s=0.0,
            )
        conversion_started = time.perf_counter()
        try:
            result = b.convert(path)
        except Exception as exc:
            logger.info("backend '%s' conversion failed: %s", backend, exc)
            return _stamp_timings(
                ConvertResult(content="", metadata={}, success=False, error=str(exc)),
                detection_s=detection_s,
                probe_s=probe_s,
                conversion_s=time.perf_counter() - conversion_started,
            )
        logger.info(
            "backend '%s' conversion %s: %s",
            backend,
            "succeeded" if result.success else "failed",
            path.name,
        )
        return _stamp_timings(
            result,
            detection_s=detection_s,
            probe_s=probe_s,
            conversion_s=time.perf_counter() - conversion_started,
        )

    ext = path.suffix.lower()
    logger.info("resolving converter for extension %s", ext or "<none>")
    converter_cls = resolve_converter(ext)
    detection_s = time.perf_counter() - started

    if converter_cls is None:
        logger.info("unsupported format %s", ext)
        return _stamp_timings(
            ConvertResult(
                content="",
                metadata={},
                success=False,
                error=f"unsupported format {ext}",
            ),
            detection_s=detection_s,
            probe_s=0.0,
            conversion_s=0.0,
        )

    logger.debug("resolved converter %s for %s", converter_cls.__name__, path.name)
    converter = converter_cls()
    conversion_started = time.perf_counter()
    result = converter.convert(path)
    conversion_s = time.perf_counter() - conversion_started
    logger.info(
        "conversion %s: %s",
        "succeeded" if result.success else "failed",
        path.name,
    )
    # A native converter never probes a backend: the stage is present and zero
    # so consumers never need a missing-key branch.
    return _stamp_timings(
        result,
        detection_s=detection_s,
        probe_s=0.0,
        conversion_s=conversion_s,
    )
