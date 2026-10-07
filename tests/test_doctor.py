"""Tests for `mid doctor` — healthy/findings paths, JSON contract, never-raise."""

from __future__ import annotations

import argparse
import json
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from mid.doctor import (
    handler_doctor,
    overall_ok,
    render_human,
    render_json_payload,
    run_checks,
)


def _args(json_flag: bool = False) -> argparse.Namespace:
    return argparse.Namespace(json=json_flag)


def _run_handler(json_flag: bool = False) -> tuple[int, str]:
    """Invoke handler_doctor, capture (exit_code, stdout)."""
    out = StringIO()
    try:
        with redirect_stdout(out):
            handler_doctor(_args(json_flag))
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
        return code, out.getvalue()
    return 0, out.getvalue()


def _all_ok_checks() -> list[dict]:
    return [
        {"name": "python", "ok": True, "status": "ok", "detail": "3.12"},
        {"name": "mid", "ok": True, "status": "ok", "detail": "mid 0.3.0"},
        {"name": "markitdown", "ok": True, "status": "ok", "detail": "markitdown 1.0"},
        {"name": "ffmpeg", "ok": True, "status": "ok", "detail": "ffmpeg 1.0 (optional)"},
        {
            "name": "backend:libreoffice",
            "ok": True,
            "status": "ok",
            "detail": "available",
            "available": True,
            "version": "1.0",
            "tool_path": "/usr/bin/soffice",
            "reason": None,
        },
        {"name": "cache/tmp", "ok": True, "status": "ok", "detail": "writable"},
        {"name": "update-checker", "ok": True, "status": "ok", "detail": "reachable"},
    ]


# ---------------------------------------------------------------------------
# Contract: real run_checks never raises, well-formed dicts
# ---------------------------------------------------------------------------


class TestRunChecksContract:
    def test_each_check_has_required_keys(self) -> None:
        checks = run_checks()
        assert isinstance(checks, list)
        assert len(checks) >= 7
        for c in checks:
            assert "name" in c and "ok" in c and "status" in c and "detail" in c
            assert isinstance(c["ok"], bool)

    def test_overall_ok_helpers(self) -> None:
        assert overall_ok(_all_ok_checks()) is True
        bad = _all_ok_checks()
        bad[3] = dict(bad[3], ok=False)
        assert overall_ok(bad) is False

    def test_render_human_summaries(self) -> None:
        assert "doctor: all checks passed" in render_human(_all_ok_checks())
        bad = _all_ok_checks()
        bad[0] = dict(bad[0], ok=False, detail="boom")
        text = render_human(bad)
        assert "doctor: 1 finding(s)" in text
        # one line per check plus summary
        assert len(text.strip().splitlines()) == len(bad) + 1

    def test_render_json_payload_keys(self) -> None:
        payload = render_json_payload(_all_ok_checks())
        assert set(("ok", "mid_version", "python", "checks")) <= set(payload.keys())
        assert payload["ok"] is True


# ---------------------------------------------------------------------------
# Handler: healthy path exits 0
# ---------------------------------------------------------------------------


class TestHandlerHealthy:
    def test_healthy_human_exit_0(self) -> None:
        with patch("mid.doctor.run_checks", return_value=_all_ok_checks()):
            code, out = _run_handler(json_flag=False)
        assert code == 0
        assert "doctor: all checks passed" in out

    def test_healthy_json_exit_0_parses(self) -> None:
        with patch("mid.doctor.run_checks", return_value=_all_ok_checks()):
            code, out = _run_handler(json_flag=True)
        assert code == 0
        payload = json.loads(out)
        assert "ok" in payload and "checks" in payload
        assert payload["ok"] is True


# ---------------------------------------------------------------------------
# Handler: missing-backend path exits 1
# ---------------------------------------------------------------------------


class TestHandlerMissingBackend:
    def _missing_libreoffice(self) -> list[dict]:
        checks = _all_ok_checks()
        for i, c in enumerate(checks):
            if c["name"] == "backend:libreoffice":
                checks[i] = {
                    "name": "backend:libreoffice",
                    "ok": False,
                    "status": "fail",
                    "detail": "LibreOffice not found (optional; install LibreOffice 7.6+)",
                    "available": False,
                    "version": None,
                    "tool_path": None,
                    "reason": "LibreOffice not found",
                }
        return checks

    def test_missing_backend_exit_1(self) -> None:
        with patch("mid.doctor.run_checks", return_value=self._missing_libreoffice()):
            code, out = _run_handler(json_flag=False)
        assert code == 1
        assert "finding(s)" in out

    def test_missing_backend_json_parses_exit_1(self) -> None:
        with patch("mid.doctor.run_checks", return_value=self._missing_libreoffice()):
            code, out = _run_handler(json_flag=True)
        assert code == 1
        payload = json.loads(out)
        assert "ok" in payload and "checks" in payload
        assert payload["ok"] is False


# ---------------------------------------------------------------------------
# Probe raising exception becomes a finding, handler never raises
# ---------------------------------------------------------------------------


class TestProbeExceptionBecomesFinding:
    def test_ffmpeg_probe_raise_becomes_finding(self) -> None:
        with patch("mid.backends.detection.which_tool", side_effect=RuntimeError("boom")):
            checks = run_checks()  # must not raise
        ffmpeg = [c for c in checks if c["name"] == "ffmpeg"]
        assert ffmpeg, "expected an ffmpeg check"
        assert ffmpeg[0]["ok"] is False

    def test_backend_is_available_raise_becomes_finding(self) -> None:
        class _Raising:
            name = "raising"

            def is_available(self, refresh: bool = False):
                raise RuntimeError("probe boom")

        from mid.backends import registry as _reg

        real = list(_reg.list_all())
        with patch.object(_reg, "list_all", return_value=real + [_Raising()]):
            checks = run_checks()  # must not raise
        raising = [c for c in checks if c["name"] == "backend:raising"]
        assert raising, "expected a backend:raising check"
        assert raising[0]["ok"] is False

    def test_handler_does_not_raise_when_probe_raises(self) -> None:
        with patch("mid.backends.detection.which_tool", side_effect=RuntimeError("boom")):
            out = StringIO()
            try:
                with redirect_stdout(out):
                    handler_doctor(_args(False))
            except SystemExit as exc:
                assert exc.code in (0, 1)
            except Exception:
                raise AssertionError("handler_doctor raised instead of exiting")
            else:
                raise AssertionError("handler_doctor should sys.exit")

    def test_handler_unexpected_error_exits_1_without_traceback(self) -> None:
        with patch("mid.doctor.run_checks", side_effect=RuntimeError("total boom")):
            code, out = _run_handler(json_flag=False)
        assert code == 1
        assert "finding" in out.lower()
        assert "Traceback" not in out


# ---------------------------------------------------------------------------
# CLI wiring: doctor subcommand exists with --json
# ---------------------------------------------------------------------------


class TestCliWiring:
    def test_doctor_parser_has_json_flag(self) -> None:
        from mid.cli import setup_parser

        parser = setup_parser()
        args = parser.parse_args(["doctor"])
        assert args.command == "doctor"
        assert getattr(args, "json", None) is False
        args2 = parser.parse_args(["doctor", "--json"])
        assert args2.json is True

    def test_cli_doctor_dispatches(self) -> None:
        import sys as _sys
        from contextlib import redirect_stderr
        from mid.cli import main

        old_argv = _sys.argv
        _sys.argv = ["mid", "doctor"]
        out, err = StringIO(), StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                with patch("mid.doctor.run_checks", return_value=_all_ok_checks()):
                    main()
            code = 0
        except SystemExit as exc:
            code = exc.code if exc.code is not None else 0
        finally:
            _sys.argv = old_argv
        assert code == 0
        assert "doctor:" in out.getvalue()
        # logs stay on stderr; human report on stdout
        assert "Traceback" not in err.getvalue()
