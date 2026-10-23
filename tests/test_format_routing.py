"""Tests for issue #42 — ODF/RTF routing through an auto-detected backend.

Strict TDD: `.odt/.ods/.odp/.rtf` have no native converter. They must convert
without an explicit `--backend` when a backend that declares them is available,
and fail with an actionable exit 3 when it is not.
"""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pytest

from mid.backends.base import Availability, Backend
from mid.backends.registry import registry
from mid.cli import main
from mid.models import ConvertResult

ROUTED_EXTENSIONS = (".odt", ".ods", ".odp", ".rtf")


class FakeLibreOfficeBackend(Backend):
    """Declares the ODF/RTF extensions and reports what the test needs."""

    def __init__(self, *, available: bool, reason: str | None = None) -> None:
        super().__init__()
        self.name = "libreoffice"
        self.display_name = "LibreOffice"
        self.supported_extensions = frozenset(
            {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"}
        )
        self.required_tools = tuple()
        self._available = available
        self._reason = reason
        self.convert_calls: list[Path] = []

    def probe(self) -> Availability:
        return Availability(
            available=self._available,
            version="7.6",
            tool_path="/usr/bin/soffice",
            reason=self._reason,
            checked_at=datetime.now(timezone.utc),
        )

    def convert(self, path: Path) -> ConvertResult:
        self.convert_calls.append(path)
        return ConvertResult(content="converted by backend", metadata={}, success=True, error=None)


def _run(args: list[str]) -> tuple[int, str, str]:
    old_argv = sys.argv
    sys.argv = ["mid"] + args
    out = StringIO()
    err = StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            main()
        return 0, out.getvalue(), err.getvalue()
    except SystemExit as e:
        return e.code if e.code is not None else 0, out.getvalue(), err.getvalue()
    finally:
        sys.argv = old_argv


@pytest.fixture
def clean_registry():
    original = list(registry.list_all())
    registry.clear()
    yield
    registry.clear()
    for backend in original:
        registry.register(backend)


@pytest.mark.parametrize("ext", ROUTED_EXTENSIONS)
def test_routed_format_converts_without_backend_flag(clean_registry, tmp_path: Path, ext: str) -> None:
    backend = FakeLibreOfficeBackend(available=True)
    registry.register(backend)
    source = tmp_path / f"sample{ext}"
    source.write_bytes(b"payload")

    code, out, err = _run(["convert", str(source)])

    assert code == 0, f"stderr: {err}"
    assert "converted by backend" in out
    assert backend.convert_calls == [source]
    # Auto-routing must not leak guidance onto stderr for a normal conversion.
    assert "unsupported format" not in err


@pytest.mark.parametrize("ext", ROUTED_EXTENSIONS)
def test_routed_format_fails_with_actionable_exit_when_backend_unavailable(clean_registry, tmp_path: Path, ext: str) -> None:
    registry.register(FakeLibreOfficeBackend(available=False, reason="LibreOffice not found — install LibreOffice 7.6+"))
    source = tmp_path / f"sample{ext}"
    source.write_bytes(b"payload")

    code, out, err = _run(["convert", str(source)])

    assert code == 3
    assert out == ""
    # A wrong refusal outranks a missing one: the message must name the format,
    # the backend that would handle it, and the runnable exit.
    assert ext in err
    assert "libreoffice" in err.lower()
    assert "install LibreOffice 7.6+" in err
    assert "--backend libreoffice" in err


def test_unknown_extension_keeps_the_unsupported_format_error(clean_registry, tmp_path: Path) -> None:
    registry.register(FakeLibreOfficeBackend(available=True))
    source = tmp_path / "sample.foo"
    source.write_bytes(b"payload")

    code, out, err = _run(["convert", str(source)])

    assert code == 3
    assert "unsupported format .foo" in err
    # Nothing may be probed for a format no backend declares.
    assert "libreoffice" not in err


def test_explicit_backend_still_wins_over_auto_routing(clean_registry, tmp_path: Path) -> None:
    backend = FakeLibreOfficeBackend(available=True)
    registry.register(backend)
    source = tmp_path / "sample.odt"
    source.write_bytes(b"payload")

    code, out, err = _run(["convert", str(source), "--backend", "libreoffice"])

    assert code == 0
    assert "converted by backend" in out


def test_json_output_stays_pure_when_auto_routed(clean_registry, tmp_path: Path) -> None:
    registry.register(FakeLibreOfficeBackend(available=True))
    source = tmp_path / "sample.odt"
    source.write_bytes(b"payload")

    code, out, err = _run(["convert", str(source), "--json"])

    assert code == 0, f"stderr: {err}"
    payload = json.loads(out)  # stdout must be valid JSON only
    assert payload["content"] == "converted by backend"
    assert payload["metadata"]["format"] == "odt"


def test_list_formats_reports_backend_only_formats_on_a_third_line(clean_registry) -> None:
    registry.register(FakeLibreOfficeBackend(available=True))

    code, out, err = _run(["--list-formats"])

    assert code == 0
    lines = out.strip().splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("Supported:")
    assert lines[1].startswith("Legacy (migrate first):")
    backend_line = lines[2]
    assert backend_line.startswith("Via backend (auto-detected):")
    for ext in ROUTED_EXTENSIONS:
        assert ext in backend_line
    # Formats with a native converter must not be advertised as backend-only.
    for ext in (".docx", ".pdf", ".xlsx", ".pptx"):
        assert ext not in backend_line


def test_list_formats_keeps_two_lines_when_no_backend_adds_formats(clean_registry) -> None:
    code, out, err = _run(["--list-formats"])

    assert code == 0
    lines = out.strip().splitlines()
    assert len(lines) == 2
    assert "Via backend" not in out
