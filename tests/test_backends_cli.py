"""CLI tests for --backend and --list-backends — strict TDD.

Covers CLI-09..11: unknown 2, unavailable 3, list reason, no-flag legacy 3.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from mid.backends.base import Availability, Backend
from mid.backends.registry import registry
from mid.models import ConvertResult


class FakeBackend(Backend):
    def __init__(self, name="fake-a", available=True, reason=None):
        super().__init__()
        self.name = name
        self.display_name = name
        self.supported_extensions = frozenset({".doc"})
        self.required_tools = tuple()
        self._available = available
        self._reason = reason

    def probe(self) -> Availability:
        return Availability(
            available=self._available,
            version="1.0",
            tool_path="/bin/fake",
            reason=self._reason,
            checked_at=datetime.now(timezone.utc),
        )

    def convert(self, path: Path) -> ConvertResult:
        return ConvertResult(content="ok", metadata={}, success=True, error=None)


@pytest.fixture(autouse=True)
def clean_registry():
    original = list(registry.list_all())
    registry.clear()
    yield
    registry.clear()
    for b in original:
        try:
            registry.register(b)
        except ValueError:
            pass


def test_list_backends_shows_reason(capsys):
    registry.register(FakeBackend(name="fake-a", available=True))
    registry.register(FakeBackend(name="fake-b", available=False, reason="soffice not found — install LibreOffice"))
    from mid.cli import main

    # Patch sys.argv
    with patch.object(sys, "argv", ["mid", "--list-backends"]):
        main()
    out = capsys.readouterr().out
    assert "fake-a: available" in out
    assert "fake-b: unavailable" in out
    assert "soffice not found" in out


def test_convert_unknown_backend_exits_2(tmp_path, capsys):
    registry.register(FakeBackend(name="fake-a"))
    registry.register(FakeBackend(name="fake-b"))
    f = tmp_path / "sample.doc"
    f.write_text("x", encoding="utf-8")
    from mid.cli import main

    with patch.object(sys, "argv", ["mid", "convert", str(f), "--backend", "unknown"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "unknown backend" in err.lower()
    assert "available backends" in err.lower()


def test_convert_unavailable_exits_3(tmp_path, capsys):
    registry.register(FakeBackend(name="soffice", available=False, reason="soffice not found — install LibreOffice"))
    f = tmp_path / "sample.doc"
    f.write_text("x", encoding="utf-8")
    from mid.cli import main

    with patch.object(sys, "argv", ["mid", "convert", str(f), "--backend", "soffice"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 3
    err = capsys.readouterr().err
    assert "unavailable" in err.lower()
    assert "soffice not found" in err


def test_no_flag_preserves_legacy_exit_3(tmp_path, capsys):
    # no backend registered needed, legacy placeholder behavior
    f = tmp_path / "sample.doc"
    f.write_text("x", encoding="utf-8")
    from mid.cli import main

    with patch.object(sys, "argv", ["mid", "convert", str(f)]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 3
    err = capsys.readouterr().err
    assert "legacy" in err.lower()


def test_list_formats_frozen(capsys):
    from mid.cli import main

    with patch.object(sys, "argv", ["mid", "--list-formats"]):
        main()
    out = capsys.readouterr().out
    assert out.startswith("Supported:")
    lines = out.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("Supported:")
    assert lines[1].startswith("Legacy")


class FakeOptInBackend(FakeBackend):
    def __init__(self, name="fake-office", available=False, reason=None):
        super().__init__(name=name, available=available, reason=reason)
        self.opt_in = True
        self.probe_calls = 0

    def probe(self) -> Availability:
        self.probe_calls += 1
        return super().probe()


def test_convert_opt_in_backend_is_probed_on_explicit_selection(tmp_path, capsys):
    # Explicit --backend is consent to probe: the opt-in gate must not block it.
    registry.register(FakeOptInBackend(available=False, reason="Office not detected — install Word/Excel"))
    f = tmp_path / "sample.doc"
    f.write_text("x", encoding="utf-8")
    from mid.cli import main

    with patch.object(sys, "argv", ["mid", "convert", str(f), "--backend", "fake-office"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 3
    err = capsys.readouterr().err
    assert "Office not detected" in err
    assert "opt-in" not in err.lower()


def test_convert_opt_in_available_succeeds(tmp_path, capsys):
    registry.register(FakeOptInBackend(available=True))
    f = tmp_path / "in.doc"
    f.write_text("x", encoding="utf-8")
    from mid.cli import main

    with patch.object(sys, "argv", ["mid", "convert", str(f), "--backend", "fake-office"]):
        main()
    out = capsys.readouterr().out
    assert "ok" in out


def test_convert_success_exit_0(tmp_path, capsys):
    # register available backend and convert
    registry.register(FakeBackend(name="fake", available=True))
    f = tmp_path / "in.doc"
    f.write_text("x", encoding="utf-8")
    from mid.cli import main

    with patch.object(sys, "argv", ["mid", "convert", str(f), "--backend", "fake"]):
        main()
    # no SystemExit means 0, output contains ok
    out = capsys.readouterr().out
    assert "ok" in out
