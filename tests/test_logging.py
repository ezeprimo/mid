"""Tests for structured logging: levels, env fallback, file handler, stdout purity."""

from __future__ import annotations

import json
import logging
import sys
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest

from mid.cli import main, setup_parser
from mid.logging_setup import setup_logging


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_logging():
    """Reset root logger around each test and scrub MID_* / NO_COLOR env."""
    import os

    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    for h in saved_handlers:
        root.removeHandler(h)
    saved_env = {k: os.environ.pop(k, None) for k in ("MID_VERBOSE", "MID_LOG_FILE", "NO_COLOR")}
    try:
        yield
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
        for h in saved_handlers:
            root.addHandler(h)
        root.setLevel(saved_level)
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v


def _run(args: list[str]) -> tuple[int, str, str]:
    old_argv = sys.argv
    sys.argv = ["mid"] + args
    out, err = StringIO(), StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            main()
        return 0, out.getvalue(), err.getvalue()
    except SystemExit as e:
        return e.code if e.code is not None else 0, out.getvalue(), err.getvalue()
    finally:
        sys.argv = old_argv


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------


class TestLevels:
    def test_default_is_warning(self) -> None:
        setup_logging()
        assert logging.getLogger().level == logging.WARNING

    def test_v1_is_info(self) -> None:
        setup_logging(verbose_count=1)
        assert logging.getLogger().level == logging.INFO

    def test_v2_is_debug(self) -> None:
        setup_logging(verbose_count=2)
        assert logging.getLogger().level == logging.DEBUG

    def test_v3_stays_debug(self) -> None:
        setup_logging(verbose_count=5)
        assert logging.getLogger().level == logging.DEBUG


# ---------------------------------------------------------------------------
# Env fallback
# ---------------------------------------------------------------------------


class TestEnvFallback:
    def test_mid_verbose_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MID_VERBOSE", "1")
        setup_logging()
        assert logging.getLogger().level == logging.INFO

    def test_mid_verbose_env_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MID_VERBOSE", "2")
        setup_logging()
        assert logging.getLogger().level == logging.DEBUG

    def test_cli_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MID_VERBOSE", "2")
        setup_logging(verbose_count=0)
        assert logging.getLogger().level == logging.WARNING

    def test_mid_log_file_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        target = tmp_path / "env.log"
        monkeypatch.setenv("MID_LOG_FILE", str(target))
        setup_logging(verbose_count=2)
        logging.getLogger("mid.test_env").debug("env-file-marker")
        for h in logging.getLogger().handlers:
            try:
                h.flush()
            except Exception:
                pass
        assert target.exists()
        assert "env-file-marker" in target.read_text(encoding="utf-8")

    def test_invalid_env_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MID_VERBOSE", "bogus")
        setup_logging()
        assert logging.getLogger().level == logging.WARNING


# ---------------------------------------------------------------------------
# Handlers: stderr-only, file append, idempotent, format
# ---------------------------------------------------------------------------


class TestHandlers:
    def test_console_goes_to_stderr_not_stdout(self, capsys: pytest.CaptureFixture) -> None:
        setup_logging(verbose_count=2)
        logging.getLogger("mid.test_stderr").debug("stderr-only-marker")
        captured = capsys.readouterr()
        assert "stderr-only-marker" in captured.err
        assert "stderr-only-marker" not in captured.out

    def test_format_has_timestamp_level_module(self, capsys: pytest.CaptureFixture) -> None:
        setup_logging(verbose_count=2)
        logging.getLogger("mid.test_format").debug("format-marker")
        captured = capsys.readouterr()
        line = next(ln for ln in captured.err.splitlines() if "format-marker" in ln)
        assert "DEBUG" in line
        assert "mid.test_format" in line

    def test_log_file_writes_without_stdout_pollution(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        target = tmp_path / "mid.log"
        setup_logging(verbose_count=2, log_file=str(target))
        logging.getLogger("mid.test_file").info("file-marker-123")
        for h in logging.getLogger().handlers:
            try:
                h.flush()
            except Exception:
                pass
        captured = capsys.readouterr()
        assert "file-marker-123" not in captured.out
        assert target.exists()
        assert "file-marker-123" in target.read_text(encoding="utf-8")

    def test_idempotent_no_duplicate_handlers(self) -> None:
        setup_logging(verbose_count=1)
        first = len(logging.getLogger().handlers)
        setup_logging(verbose_count=1)
        setup_logging(verbose_count=1)
        assert len(logging.getLogger().handlers) == first


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


class TestCliFlags:
    def test_global_verbose_parses(self) -> None:
        args = setup_parser().parse_args(["-vv", "convert", "f.docx"])
        assert args.verbose == 2

    def test_convert_subcommand_verbose(self) -> None:
        args = setup_parser().parse_args(["convert", "f.docx", "-vv"])
        assert args.verbose == 2

    def test_subcommand_overrides_global(self) -> None:
        args = setup_parser().parse_args(["-v", "convert", "f.docx", "-vv"])
        assert args.verbose == 2

    def test_batch_flags_parse(self) -> None:
        args = setup_parser().parse_args(["batch", "indir", "-o", "outdir", "-v", "--log-file", "x.log"])
        assert args.verbose == 1
        assert args.log_file == "x.log"

    def test_verbose_does_not_break_help(self) -> None:
        code, out, _ = _run(["convert", "--help"])
        assert code == 0
        assert "usage" in out.lower()


class TestJsonStaysParseable:
    def test_json_parseable_with_vv(self, tmp_path: Path, make_docx) -> None:
        src = make_docx(tmp_path / "logged.docx", text="logging json e2e")
        code, out, _ = _run(["convert", str(src), "--json", "-vv"])
        assert code == 0
        payload = json.loads(out)
        assert payload["metadata"]["success"] is True
        assert "logging json e2e" in payload["content"]
