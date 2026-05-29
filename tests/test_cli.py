"""Tests for the CLI layer — argument parsing, exit codes, JSON output."""

from __future__ import annotations

import json
import importlib.util
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

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
        assert "mid 0.1.0" in out

    def test_short_flag(self) -> None:
        code, out, err = _run(["-V"])
        assert code == 0
        assert "mid 0.1.0" in out


class TestListFormats:
    def test_lists_all_seven(self) -> None:
        code, out, err = _run(["--list-formats"])
        assert code == 0
        for ext in (".docx", ".xlsx", ".pptx", ".pdf", ".doc", ".xls", ".ppt"):
            assert ext in out

    def test_format_order(self) -> None:
        code, out, err = _run(["--list-formats"])
        formats = out.strip().split()
        assert formats == sorted(formats)


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

    def test_unsupported_format(self) -> None:
        code, out, err = _run(["convert", "image.png"])
        assert code == 3
        assert "unsupported format" in err.lower()

    def test_legacy_format_exit_code(self, tmp_path: Path) -> None:
        src = tmp_path / "old.doc"
        src.write_text("fake", encoding="utf-8")
        code, out, err = _run(["convert", str(src)])
        assert code == 3
        assert "legacy" in err.lower()


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
