"""Tests for the CLI layer — argument parsing, exit codes, JSON output."""

from __future__ import annotations

import json
import importlib.util
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from mid import __version__
from mid.backends.base import Availability, Backend
from mid.backends.registry import registry
from mid.cli import main
from mid.models import ConvertResult


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------


def _run(args: list[str]) -> tuple[int, str, str]:
    """Invoke ``main()`` with *args* and capture ``(exit_code, stdout, stderr)``."""
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


# ===========================================================================
# Top-level flags
# ===========================================================================


class TestVersion:
    def test_long_flag(self) -> None:
        code, out, err = _run(["--version"])
        assert code == 0
        assert f"mid {__version__}" in out

    def test_short_flag(self) -> None:
        code, out, err = _run(["-V"])
        assert code == 0
        assert f"mid {__version__}" in out


class TestListFormats:
    def test_supported_and_legacy_separated(self) -> None:
        code, out, err = _run(["--list-formats"])
        assert code == 0
        assert "Supported:" in out
        assert "Legacy (migrate first):" in out
        assert out.index("Supported:") < out.index("Legacy (migrate first):")

    def test_supported_formats_present(self) -> None:
        code, out, err = _run(["--list-formats"])
        supported_line = [ln for ln in out.splitlines() if ln.startswith("Supported:")][0]
        for ext in (".docx", ".xlsx", ".pptx", ".pdf"):
            assert ext in supported_line

    def test_legacy_formats_present(self) -> None:
        code, out, err = _run(["--list-formats"])
        legacy_line = [ln for ln in out.splitlines() if ln.startswith("Legacy")][0]
        for ext in (".doc", ".xls", ".ppt"):
            assert ext in legacy_line

    @pytest.fixture
    def builtin_backends(self):
        """Guarantee the built-in backends are registered for this test.

        Registration happens on import, so a test that cleared the registry
        earlier in the session would otherwise change this output.
        """
        import mid.backends  # noqa: F401
        from mid.backends.libreoffice import LibreOfficeBackend
        from mid.backends.registry import registry

        if registry.get("libreoffice") is None:
            registry.register(LibreOfficeBackend())
        yield

    def test_output_format_contract(self, builtin_backends) -> None:
        """Verify exact output shape: 3 lines, space-separated extensions."""
        code, out, err = _run(["--list-formats"])
        assert code == 0
        lines = out.strip().splitlines()
        assert len(lines) == 3
        supported_line, legacy_line, backend_line = lines
        assert supported_line.startswith("Supported:")
        assert legacy_line.startswith("Legacy (migrate first):")
        assert backend_line.startswith("Via backend (auto-detected):")
        # Each extension should be separated by a single space
        for line, label in (
            (supported_line, "Supported: "),
            (legacy_line, "Legacy (migrate first): "),
            (backend_line, "Via backend (auto-detected): "),
        ):
            exts = line.replace(label, "").split()
            assert exts, f"{label} must list at least one extension"
            assert all(e.startswith(".") for e in exts)
            assert exts == sorted(exts), f"{label} must be sorted"
        # The backend line must not repeat formats a native converter handles.
        supported_exts = set(supported_line.replace("Supported: ", "").split())
        legacy_exts = set(legacy_line.replace("Legacy (migrate first): ", "").split())
        backend_exts = set(backend_line.replace("Via backend (auto-detected): ", "").split())
        assert backend_exts.isdisjoint(supported_exts | legacy_exts)


# ===========================================================================
# convert command — error paths
# ===========================================================================


class TestConvertErrors:
    def test_no_file_argument(self) -> None:
        code, out, err = _run(["convert"])
        assert code == 2
        assert "FILE is required" in err

    def test_file_not_found(self) -> None:
        code, out, err = _run(["convert", "nonexistent.docx"])
        assert code == 2
        assert "file not found" in err.lower()

    def test_unsupported_format(self, tmp_path: Path) -> None:
        src = tmp_path / "image.png"
        src.write_text("fake", encoding="utf-8")
        code, out, err = _run(["convert", str(src)])
        assert code == 3
        assert "unsupported format" in err.lower()

    def test_legacy_format_exit_code(self, tmp_path: Path) -> None:
        src = tmp_path / "old.doc"
        src.write_text("fake", encoding="utf-8")
        code, out, err = _run(["convert", str(src)])
        assert code == 3
        assert "legacy" in err.lower()

    def test_json_with_conversion_failure(self, tmp_path: Path) -> None:
        """--json with a conversion failure should still exit 1 with no JSON output."""
        src = tmp_path / "broken.docx"
        src.write_text("garbage", encoding="utf-8")

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.side_effect = RuntimeError("corrupt file")

            code, out, err = _run(["convert", str(src), "--json"])

        assert code == 1
        assert out == ""  # no JSON output on failure

    def test_extensionless_file_returns_unsupported(self, tmp_path: Path) -> None:
        """A real file without extension should exit 3 with unsupported format."""
        src = tmp_path / "Makefile"
        src.write_text("some content", encoding="utf-8")
        code, out, err = _run(["convert", str(src)])
        assert code == 3
        assert "unsupported format" in err.lower()


# ===========================================================================
# convert command — success paths
# ===========================================================================


class TestConvertSuccess:
    def test_stdout_output(self, tmp_path: Path) -> None:
        """Default output goes to stdout."""
        src = tmp_path / "test.docx"
        src.write_text("", encoding="utf-8")

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = "# Works\n\nHello"

            code, out, err = _run(["convert", str(src)])

        assert code == 0
        assert "# Works" in out

    def test_output_file(self, tmp_path: Path) -> None:
        """-o writes to the given file instead of stdout."""
        src = tmp_path / "test.docx"
        src.write_text("", encoding="utf-8")
        dst = tmp_path / "out.md"

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = "# File output"

            code, out, err = _run(["convert", str(src), "-o", str(dst)])

        assert code == 0
        assert out == ""  # nothing on stdout
        assert dst.read_text(encoding="utf-8") == "# File output"

    def test_output_file_creates_missing_parent_dirs(self, tmp_path: Path) -> None:
        """-o creates missing parent directories before writing."""
        src = tmp_path / "test.docx"
        src.write_text("", encoding="utf-8")
        dst = tmp_path / "nested" / "missing" / "out.md"

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = "# Nested output"

            code, out, err = _run(["convert", str(src), "-o", str(dst)])

        assert code == 0
        assert out == ""
        assert err == ""
        assert dst.read_text(encoding="utf-8") == "# Nested output"

    def test_output_write_failure_uses_cli_error_path(self, tmp_path: Path) -> None:
        """Write failures should exit with conversion error, not traceback."""
        src = tmp_path / "test.docx"
        src.write_text("", encoding="utf-8")
        dst = tmp_path / "out.md"

        with patch("markitdown.MarkItDown") as MockMD, patch.object(Path, "write_text", side_effect=OSError("disk full")):
            inst = MockMD.return_value
            inst.convert.return_value.text_content = "# File output"

            code, out, err = _run(["convert", str(src), "-o", str(dst)])

        assert code == 1
        assert "conversion failed" in err.lower()
        assert "could not write output file" in err.lower()

    def test_json_output_contract(self, tmp_path: Path) -> None:
        """--json emits the standard JSON contract."""
        src = tmp_path / "report.docx"
        src.write_text("", encoding="utf-8")

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = "# JSON test"

            code, out, err = _run(["convert", str(src), "--json"])

        assert code == 0
        payload = json.loads(out)
        assert payload["content"] == "# JSON test"
        assert payload["metadata"]["source"] == "report.docx"
        assert payload["metadata"]["format"] == "docx"
        assert payload["metadata"]["success"] is True
        assert payload["error"] is None

    def test_conversion_failure(self, tmp_path: Path) -> None:
        """When MarkItDown fails → exit 1."""
        src = tmp_path / "broken.docx"
        src.write_text("garbage", encoding="utf-8")

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.side_effect = RuntimeError("corrupt file")

            code, out, err = _run(["convert", str(src)])

        assert code == 1
        assert "conversion failed" in err.lower()

    def test_json_precedence_over_output_file(self, tmp_path: Path) -> None:
        """When both --json and -o are passed, --json wins (stdout)."""
        src = tmp_path / "test.docx"
        src.write_text("", encoding="utf-8")
        dst = tmp_path / "out.md"

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = "# JSON wins"

            code, out, err = _run(["convert", str(src), "--json", "-o", str(dst)])

        assert code == 0
        # JSON on stdout
        payload = json.loads(out)
        assert payload["content"] == "# JSON wins"
        # -o file should NOT be written when --json is used
        assert not dst.exists()


class TestConvertRealE2E:
    """Real end-to-end CLI conversion against a generated .docx file."""

    def _require_markitdown(self) -> None:
        if importlib.util.find_spec("markitdown") is None:
            pytest.fail(
                "Real E2E tests require markitdown in local .venv. "
                "Install with: .venv\\Scripts\\python -m pip install 'markitdown[all]'",
            )

    def test_real_docx_to_stdout(self, tmp_path: Path, make_docx) -> None:
        self._require_markitdown()
        src = make_docx(tmp_path / "real.docx", text="E2E real docx content")

        code, out, err = _run(["convert", str(src)])

        assert code == 0
        assert "E2E real docx content" in out
        assert err == ""

    def test_real_docx_to_output_file(self, tmp_path: Path, make_docx) -> None:
        self._require_markitdown()
        src = make_docx(tmp_path / "real-output.docx", text="E2E output target")
        dst = tmp_path / "result.md"

        code, out, err = _run(["convert", str(src), "-o", str(dst)])

        assert code == 0
        assert out == ""
        assert err == ""
        assert "E2E output target" in dst.read_text(encoding="utf-8")


# ===========================================================================
# help
# ===========================================================================


class TestHelp:
    def test_help_short_flag(self) -> None:
        code, out, err = _run(["-h"])
        assert code == 0
        assert "convert" in out
        assert "batch" in out

    def test_help_long_flag(self) -> None:
        code, out, err = _run(["--help"])
        assert code == 0
        assert "MarkItDown" in out

    def test_help_subcommand(self) -> None:
        code, out, err = _run(["help"])
        assert code == 0
        assert "convert" in out

    def test_help_convert_subcommand(self) -> None:
        code, out, err = _run(["help", "convert"])
        assert code == 0
        assert "FILE" in out

    def test_help_batch_subcommand(self) -> None:
        code, out, err = _run(["help", "batch"])
        assert code == 0
        assert "INPUT_DIR" in out or "input" in out

    def test_help_unknown_topic(self) -> None:
        code, out, err = _run(["help", "nosuch"])
        assert code == 2


# ===========================================================================
# Edge cases
# ===========================================================================


class TestMainNoArgs:
    def test_no_args_shows_help(self) -> None:
        code, out, err = _run([])
        assert code == 0
        assert "usage:" in out.lower() or "convert" in out


# ===========================================================================
# JSON timings (issue #45)
# ===========================================================================


class TestConvertJsonTimings:
    """`convert --json` reports per-stage timings without breaking the schema."""

    def test_native_json_carries_every_stage_key(self, tmp_path: Path) -> None:
        src = tmp_path / "test.docx"
        src.write_text("", encoding="utf-8")

        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = "# Hello"

            code, out, err = _run(["convert", str(src), "--json"])

        assert code == 0, f"stderr: {err}"
        payload = json.loads(out)

        # Additive only: the pre-existing schema is untouched.
        assert payload["content"] == "# Hello"
        assert payload["metadata"]["source"] == "test.docx"
        assert payload["metadata"]["format"] == "docx"
        assert payload["metadata"]["success"] is True
        assert payload["error"] is None

        timings = payload["timings"]
        assert set(timings) == {"detection_ms", "probe_ms", "conversion_ms", "total_ms"}
        for key, value in timings.items():
            assert isinstance(value, int), f"{key} must be an integer of milliseconds, got {type(value)}"
            assert not isinstance(value, bool)
            assert value >= 0, f"{key} must never be negative"

        # The stages are measured inside one wall clock, so their sum is bounded by it.
        stages = timings["detection_ms"] + timings["probe_ms"] + timings["conversion_ms"]
        assert stages <= timings["total_ms"]

        # A native converter never probes a backend: the key is present and zero so
        # consumers never need a KeyError branch.
        assert timings["probe_ms"] == 0

    def test_conversion_stage_reflects_real_elapsed_time(self, tmp_path: Path) -> None:
        src = tmp_path / "slow.docx"
        src.write_text("", encoding="utf-8")

        def slow_convert(_path: object) -> object:
            time.sleep(0.03)
            return type("R", (), {"text_content": "# Slow"})()

        with patch("markitdown.MarkItDown") as MockMD:
            MockMD.return_value.convert.side_effect = slow_convert

            code, out, err = _run(["convert", str(src), "--json"])

        assert code == 0, f"stderr: {err}"
        timings = json.loads(out)["timings"]
        assert timings["conversion_ms"] >= 20, timings
        assert timings["total_ms"] >= timings["conversion_ms"]


class TestConvertDirectory:
    def test_convert_directory_returns_arg_error(self, tmp_path: Path) -> None:
        d = tmp_path / "somedir"
        d.mkdir()
        code, out, err = _run(["convert", str(d)])
        assert code == 2
        assert "not a file" in err.lower()


class TestListFormatsWithSubcommand:
    def test_with_subcommand_ignored(self) -> None:
        code, out, err = _run(["--list-formats", "convert"])
        assert code == 0
        assert "Supported:" in out


# ===========================================================================
# Single probe on an explicit --backend (issue #70)
# ===========================================================================


class CountingBackend(Backend):
    """Declares .doc/.odt and counts probes so a double probe is observable."""

    def __init__(self, *, available: bool = True, reason: str | None = None, probe_delay: float = 0.0) -> None:
        super().__init__()
        self.name = "counting"
        self.display_name = "Counting"
        self.supported_extensions = frozenset({".doc", ".odt"})
        self.required_tools = tuple()
        self.probe_calls = 0
        self.convert_calls: list[Path] = []
        self._available = available
        self._reason = reason
        self._probe_delay = probe_delay

    def probe(self) -> Availability:
        self.probe_calls += 1
        if self._probe_delay:
            time.sleep(self._probe_delay)
        return Availability(
            available=self._available,
            version="7.6",
            tool_path="/usr/bin/soffice",
            reason=self._reason,
            checked_at=datetime.now(timezone.utc),
        )

    def convert(self, path: Path) -> ConvertResult:
        self.convert_calls.append(path)
        return ConvertResult(content="# from fake backend", metadata={}, success=True, error=None)


@pytest.fixture
def probe_registry():
    """Empty registry that restores the built-ins afterwards."""
    original = list(registry.list_all())
    registry.clear()
    yield registry
    registry.clear()
    for backend in original:
        registry.register(backend)


class TestConvertBackendSingleProbe:
    """`convert --backend` must probe exactly once (#70)."""

    def test_explicit_backend_probes_once(self, probe_registry, tmp_path: Path) -> None:
        backend = CountingBackend()
        probe_registry.register(backend)
        src = tmp_path / "legacy.odt"
        src.write_bytes(b"payload")

        code, out, err = _run(["convert", str(src), "--backend", "counting"])

        assert code == 0, f"stderr: {err}"
        assert out == "# from fake backend\n"
        assert err == ""
        assert backend.probe_calls == 1
        assert backend.convert_calls == [src]

    def test_unavailable_backend_exits_3_after_a_single_probe(self, probe_registry, tmp_path: Path) -> None:
        backend = CountingBackend(available=False, reason="soffice missing")
        probe_registry.register(backend)
        src = tmp_path / "legacy.odt"
        src.write_bytes(b"payload")

        code, out, err = _run(["convert", str(src), "--backend", "counting"])

        assert code == 3
        assert out == ""
        assert err == "error: backend 'counting' unavailable: soffice missing\n"
        assert backend.probe_calls == 1
        assert backend.convert_calls == []

    def test_json_reports_the_single_probe_in_timings(self, probe_registry, tmp_path: Path) -> None:
        # A slow probe keeps `probe_ms` safely above the 1 ms truncation floor.
        backend = CountingBackend(probe_delay=0.05)
        probe_registry.register(backend)
        src = tmp_path / "legacy.odt"
        src.write_bytes(b"payload")

        code, out, err = _run(["convert", str(src), "--backend", "counting", "--json"])

        assert code == 0, f"stderr: {err}"
        payload = json.loads(out)
        assert payload["content"] == "# from fake backend"
        assert backend.probe_calls == 1

        timings = payload["timings"]
        assert set(timings) == {"detection_ms", "probe_ms", "conversion_ms", "total_ms"}
        for key, value in timings.items():
            assert isinstance(value, int), f"{key} must be an integer of milliseconds"
            assert not isinstance(value, bool)
            assert value >= 0

        # The engine no longer probes on this path, so the CLI's own measurement
        # is the only thing that can make probe_ms non-zero.
        assert timings["probe_ms"] >= 20, timings
        stages = timings["detection_ms"] + timings["probe_ms"] + timings["conversion_ms"]
        assert stages <= timings["total_ms"], timings
