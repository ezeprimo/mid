"""Tests for update checker — cache, semver, guards, banner, throttle."""

from __future__ import annotations

import datetime
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from mid import __version__
from mid.cli import main
from mid.update_checker import (
    CACHE_TTL,
    _read_cache,
    _write_cache,
    check_and_notify,
    fetch_latest_version,
    get_cache_path,
    is_newer,
    should_check,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(args: list[str]) -> tuple[int, str, str]:
    """Invoke main() with args and capture (exit_code, stdout, stderr)."""
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


# ---------------------------------------------------------------------------
# get_cache_path
# ---------------------------------------------------------------------------


class TestGetCachePath:
    def test_primary_uses_platformdirs(self, tmp_path: Path, monkeypatch) -> None:
        # Mock platformdirs.user_cache_dir to tmp_path
        mock_dir = str(tmp_path / "cache")
        with patch.dict("sys.modules", {}):
            # Need to simulate platformdirs available
            import types

            mod = types.ModuleType("platformdirs")

            def fake_user_cache_dir(appname: str) -> str:
                assert appname == "mid"
                return mock_dir

            mod.user_cache_dir = fake_user_cache_dir  # type: ignore[attr-defined]
            with patch.dict(sys.modules, {"platformdirs": mod}):
                # Need to reload get_cache_path's import? It does lazy import inside function,
                # so patching sys.modules is enough.
                from mid.update_checker import get_cache_path as gcp

                p = gcp()
                assert p == Path(mock_dir) / "update_cache.json"
                # parent should exist with 0700 attempt (best effort)
                assert p.parent.exists()

    def test_fallback_when_platformdirs_missing(self, tmp_path: Path, monkeypatch) -> None:
        # Simulate ImportError for platformdirs
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "platformdirs":
                raise ImportError("missing")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            # Also need to ensure platformdirs not in sys.modules
            with patch.dict(sys.modules, {"platformdirs": None}):
                # Clear module cache for update_checker's internal import attempt?
                # get_cache_path does `from platformdirs import user_cache_dir` -> will trigger ImportError
                # But we patched __import__ to raise, so it will fallback
                # Need to handle sys.modules containing None -> ImportError
                # Use monkeypatch to set HOME to tmp_path
                monkeypatch.setenv("HOME", str(tmp_path))
                # monkeypatch Path.home to tmp_path
                with patch.object(Path, "home", return_value=tmp_path):
                    p = get_cache_path()
                    assert p == tmp_path / ".config" / "mid" / ".update_cache.json"

    def test_parent_dirs_created_0700(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "newcache" / "nested")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            p = get_cache_path()
            assert p.parent.exists()
            if os.name != "nt":
                # Check perms 0700 (best effort). May be affected by umask, but check that it's at least 0700 or 0755?
                # We check that chmod was attempted; actual mode should be 0o700 if umask allows
                mode = p.parent.stat().st_mode & 0o777
                # On POSIX, expect 0o700
                assert mode == 0o700, f"expected 0700 got {oct(mode)}"


# ---------------------------------------------------------------------------
# _read_cache / _write_cache
# ---------------------------------------------------------------------------


class TestCacheIO:
    def test_read_missing_returns_none(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            assert _read_cache() is None

    def test_read_corrupt_returns_none(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            p = get_cache_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("not json {", encoding="utf-8")
            assert _read_cache() is None

    def test_read_non_dict_returns_none(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            p = get_cache_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
            assert _read_cache() is None

    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            data = {"latest_version": "0.9.0", "checked_at": "2025-01-01T00:00:00Z"}
            _write_cache(data)
            p = get_cache_path()
            assert p.exists()
            assert _read_cache() == data
            # Check no .tmp left
            assert not (p.with_suffix(p.suffix + ".tmp")).exists()
            if os.name != "nt":
                mode_file = p.stat().st_mode & 0o777
                assert mode_file == 0o600, f"expected 0600 got {oct(mode_file)}"
                mode_dir = p.parent.stat().st_mode & 0o777
                assert mode_dir == 0o700

    def test_write_atomic_via_tmp(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            # Write initial
            _write_cache({"latest_version": "1.0.0", "checked_at": "2025-01-01T00:00:00Z"})
            p = get_cache_path()
            # Patch os.replace to verify atomic
            with patch("mid.update_checker.os.replace") as mock_replace:
                _write_cache({"latest_version": "2.0.0", "checked_at": "2025-01-02T00:00:00Z"})
                assert mock_replace.called
                # ensure tmp path used
                args, _ = mock_replace.call_args
                assert str(args[0]).endswith(".tmp")
                assert args[1] == p


# ---------------------------------------------------------------------------
# is_newer
# ---------------------------------------------------------------------------


class TestIsNewer:
    def test_newer_true(self) -> None:
        assert is_newer("0.2.0", "0.1.1") is True
        assert is_newer("1.0.0", "0.9.9") is True
        assert is_newer("0.1.2", "0.1.1") is True

    def test_equal_false(self) -> None:
        assert is_newer("0.1.1", "0.1.1") is False
        assert is_newer("v0.1.1", "0.1.1") is False

    def test_older_false(self) -> None:
        assert is_newer("0.1.0", "0.1.1") is False

    def test_v_strip(self) -> None:
        assert is_newer("v0.2.0", "v0.1.1") is True
        assert is_newer("v0.2.0", "0.1.1") is True
        assert is_newer("V0.2.0", "0.1.1") is True
        assert is_newer(" v0.2.0 ", " 0.1.1 ") is True

    def test_invalid_returns_false(self) -> None:
        assert is_newer("not-a-version", "0.1.1") is False
        assert is_newer("0.2.0", "not-a-version") is False
        assert is_newer("", "0.1.1") is False
        assert is_newer("0.2.0", "") is False

    def test_fallback_without_packaging(self, monkeypatch) -> None:
        # Simulate packaging missing
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("packaging"):
                raise ImportError("no packaging")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            # Need to ensure packaging not in sys.modules
            with patch.dict(sys.modules, {"packaging": None, "packaging.version": None}):
                # Force reload? is_newer does lazy import, so patch is enough if we clear cache
                # But Python may have already imported packaging.version; remove it
                sys_modules_backup = sys.modules.copy()
                sys.modules.pop("packaging", None)
                sys.modules.pop("packaging.version", None)
                try:
                    assert is_newer("0.2.0", "0.1.1") is True
                    assert is_newer("0.1.1", "0.2.0") is False
                    assert is_newer("v0.2.0", "0.1.1") is True
                    assert is_newer("0.1.1", "0.1.1") is False
                finally:
                    sys.modules.clear()
                    sys.modules.update(sys_modules_backup)


# ---------------------------------------------------------------------------
# fetch_latest_version
# ---------------------------------------------------------------------------


class TestFetchLatest:
    def test_httpx_success(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"tag_name": "v0.5.0"}
        with patch.dict(sys.modules, {"httpx": MagicMock(get=MagicMock(return_value=mock_resp))}):
            # Need to ensure httpx mock is used
            # Patch already includes httpx; fetch will import it
            result = fetch_latest_version()
            assert result == "0.5.0"

    def test_httpx_strips_v(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"tag_name": "v1.2.3"}
        with patch.dict(sys.modules, {"httpx": MagicMock(get=MagicMock(return_value=mock_resp))}):
            assert fetch_latest_version() == "1.2.3"

    def test_httpx_non_200_returns_none(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch.dict(sys.modules, {"httpx": MagicMock(get=MagicMock(return_value=mock_resp))}):
            assert fetch_latest_version() is None

    def test_httpx_exception_returns_none(self) -> None:
        def raise_err(*args, **kwargs):
            raise RuntimeError("network fail")

        with patch.dict(sys.modules, {"httpx": MagicMock(get=raise_err)}):
            assert fetch_latest_version() is None

    def test_urllib_fallback_when_httpx_missing(self) -> None:
        # Simulate httpx ImportError, then urllib success
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "httpx":
                raise ImportError("no httpx")
            return real_import(name, *args, **kwargs)

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"tag_name": "v2.0.0"}).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: False

        with patch("builtins.__import__", side_effect=fake_import):
            with patch.dict(sys.modules, {"httpx": None}):
                sys.modules.pop("httpx", None)
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    result = fetch_latest_version()
                    assert result == "2.0.0"

    def test_fetch_timeout_silent(self) -> None:
        # httpx timeout should be silent
        def raise_timeout(*args, **kwargs):
            raise TimeoutError("timeout")

        with patch.dict(sys.modules, {"httpx": MagicMock(get=raise_timeout)}):
            assert fetch_latest_version(timeout=0.1) is None


# ---------------------------------------------------------------------------
# should_check guards
# ---------------------------------------------------------------------------


class TestShouldCheck:
    def test_non_tty_false(self, monkeypatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("MID_NO_UPDATE_CHECK", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        with patch.object(sys.stderr, "isatty", return_value=False):
            assert should_check(argv=["mid", "convert", "file.docx"]) is False

    def test_ci_truthy_false(self, monkeypatch) -> None:
        monkeypatch.setenv("CI", "1")
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert should_check(argv=["mid", "convert", "file.docx"]) is False
        monkeypatch.setenv("CI", "true")
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert should_check(argv=["mid", "convert", "file.docx"]) is False
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert should_check(argv=["mid", "convert", "file.docx"]) is False

    def test_term_dumb_false(self, monkeypatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.setenv("TERM", "dumb")
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert should_check(argv=["mid", "convert", "file.docx"]) is False
        monkeypatch.setenv("TERM", "DUMB")
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert should_check(argv=["mid", "convert", "file.docx"]) is False
        monkeypatch.setenv("TERM", "xterm")
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert should_check(argv=["mid", "convert", "file.docx"]) is True

    def test_help_flag_false(self, monkeypatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert should_check(argv=["mid", "--help"]) is False
            assert should_check(argv=["mid", "-h"]) is False
            assert should_check(argv=["mid", "--version"]) is False
            assert should_check(argv=["mid", "convert", "--help"]) is False

    def test_json_flag_false(self, monkeypatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert should_check(argv=["mid", "convert", "file.docx", "--json"]) is False
            assert should_check(argv=["mid", "--json"]) is False

    def test_list_formats_false(self, monkeypatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert should_check(argv=["mid", "--list-formats"]) is False

    def test_opt_out_env_false(self, monkeypatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        for val in ["1", "true", "True", "TRUE", "yes", "YES", "on", "ON"]:
            monkeypatch.setenv("MID_NO_UPDATE_CHECK", val)
            with patch.object(sys.stderr, "isatty", return_value=True):
                assert should_check(argv=["mid", "convert", "file.docx"]) is False, f"failed for {val}"
        monkeypatch.setenv("MID_NO_UPDATE_CHECK", "0")
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert should_check(argv=["mid", "convert", "file.docx"]) is True
        monkeypatch.setenv("MID_NO_UPDATE_CHECK", "false")
        with patch.object(sys.stderr, "isatty", return_value=True):
            assert should_check(argv=["mid", "convert", "file.docx"]) is True

    def test_trunk_allowlist(self, monkeypatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        monkeypatch.delenv("MID_NO_UPDATE_CHECK", raising=False)
        with patch.object(sys.stderr, "isatty", return_value=True):
            # Allowed
            assert should_check(argv=["mid"]) is True  # no subcommand -> ()
            assert should_check(argv=["mid", "convert", "file.docx"]) is True
            assert should_check(argv=["mid", "batch", "in", "-o", "out"]) is True
            assert should_check(argv=["mid", "help"]) is True
            assert should_check(argv=["mid", "help", "convert"]) is True  # subcommand help still allowed (first token help)
            # Not allowed
            assert should_check(argv=["mid", "unknown"]) is False
            assert should_check(argv=["mid", "convert-extra"]) is False
            # With flags before subcommand, should still detect subcommand
            assert should_check(argv=["mid", "--list-formats"]) is False  # already blocked earlier
            # Bare argv without program name
            assert should_check(argv=["convert", "file.docx"]) is True
            assert should_check(argv=["batch"]) is True
            assert should_check(argv=[]) is True  # empty -> ()

    def test_uses_sys_argv_when_none(self, monkeypatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        monkeypatch.delenv("MID_NO_UPDATE_CHECK", raising=False)
        with patch.object(sys.stderr, "isatty", return_value=True):
            old = sys.argv
            try:
                sys.argv = ["mid", "convert", "file.docx"]
                assert should_check(argv=None) is True
                sys.argv = ["mid", "--help"]
                assert should_check(argv=None) is False
            finally:
                sys.argv = old


# ---------------------------------------------------------------------------
# check_and_notify
# ---------------------------------------------------------------------------


class TestCheckAndNotify:
    def test_prints_banner_when_outdated(self, tmp_path: Path, monkeypatch) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            # Mock should_check true, isatty true
            with patch("mid.update_checker.should_check", return_value=True):
                with patch("mid.update_checker.fetch_latest_version", return_value="9.9.9"):
                    # Ensure no cache
                    # Need to make sys.stderr.isatty true via patch, but check_and_notify uses should_check mock, so not needed
                    # Capture stderr via patching sys.stderr to StringIO with isatty True
                    fake_stderr = StringIO()
                    fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                    with patch.object(sys, "stderr", fake_stderr):
                        # Also patch rich to not interfere
                        with patch.dict(sys.modules, {"rich": None, "rich.console": None}):
                            sys.modules.pop("rich", None)
                            sys.modules.pop("rich.console", None)
                            # Ensure rich import fails -> fallback to print
                            # Need to make import rich raise ImportError
                            real_import = __import__

                            def fake_import(name, *args, **kwargs):
                                if name.startswith("rich"):
                                    raise ImportError("no rich")
                                return real_import(name, *args, **kwargs)

                            with patch("builtins.__import__", side_effect=fake_import):
                                check_and_notify()
                                output = fake_stderr.getvalue()
                                assert "Update available" in output
                                assert __version__ in output
                                assert "9.9.9" in output
                                assert "curl -fsSL" in output or "irm" in output
                                # Ensure not on stdout
                                # check_and_notify should not have printed to stdout, but we didn't capture stdout here
                                # banner should contain pipx line
                                assert "pipx install" in output
                                assert "https://github.com/ezeprimo/mid/releases" in output

    def test_suppressed_when_up_to_date(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            with patch("mid.update_checker.should_check", return_value=True):
                with patch("mid.update_checker.fetch_latest_version", return_value=__version__):
                    fake_stderr = StringIO()
                    fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                    with patch.object(sys, "stderr", fake_stderr):
                        # Make rich unavailable to use plain print
                        real_import = __import__

                        def fake_import(name, *args, **kwargs):
                            if name.startswith("rich"):
                                raise ImportError("no rich")
                            return real_import(name, *args, **kwargs)

                        with patch("builtins.__import__", side_effect=fake_import):
                            check_and_notify()
                            assert fake_stderr.getvalue() == ""

    def test_suppressed_on_guards(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            with patch("mid.update_checker.should_check", return_value=False):
                with patch("mid.update_checker.fetch_latest_version") as mock_fetch:
                    fake_stderr = StringIO()
                    fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                    with patch.object(sys, "stderr", fake_stderr):
                        check_and_notify()
                        mock_fetch.assert_not_called()
                        assert fake_stderr.getvalue() == ""

    def test_throttle_uses_cache(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            now = datetime.datetime.now(datetime.timezone.utc)
            # Write cache with recent checked_at and older version (no banner expected if up-to-date? Let's make latest older)
            # For throttle test, we want second invocation to use cache not fetch.
            # We'll set cache latest to 9.9.9 and checked_at to now, then second call should not fetch but still print banner from cache
            data = {
                "latest_version": "9.9.9",
                "checked_at": now.isoformat().replace("+00:00", "Z"),
            }
            _write_cache(data)

            with patch("mid.update_checker.should_check", return_value=True):
                with patch("mid.update_checker.fetch_latest_version") as mock_fetch:
                    fake_stderr = StringIO()
                    fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                    with patch.object(sys, "stderr", fake_stderr):
                        real_import = __import__

                        def fake_import(name, *args, **kwargs):
                            if name.startswith("rich"):
                                raise ImportError("no rich")
                            return real_import(name, *args, **kwargs)

                        with patch("builtins.__import__", side_effect=fake_import):
                            check_and_notify()
                            # Should NOT have called fetch because within TTL
                            mock_fetch.assert_not_called()
                            # Should have printed banner from cache
                            assert "9.9.9" in fake_stderr.getvalue()

    def test_throttle_expired_fetches(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            old_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=CACHE_TTL + 100)
            data = {
                "latest_version": "0.0.1",
                "checked_at": old_time.isoformat().replace("+00:00", "Z"),
            }
            _write_cache(data)

            with patch("mid.update_checker.should_check", return_value=True):
                with patch("mid.update_checker.fetch_latest_version", return_value="9.9.9") as mock_fetch:
                    fake_stderr = StringIO()
                    fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                    with patch.object(sys, "stderr", fake_stderr):
                        real_import = __import__

                        def fake_import(name, *args, **kwargs):
                            if name.startswith("rich"):
                                raise ImportError("no rich")
                            return real_import(name, *args, **kwargs)

                        with patch("builtins.__import__", side_effect=fake_import):
                            check_and_notify()
                            mock_fetch.assert_called_once()
                            assert "9.9.9" in fake_stderr.getvalue()
                            # Cache should be updated
                            new_cache = _read_cache()
                            assert new_cache is not None
                            assert new_cache["latest_version"] == "9.9.9"

    def test_silent_on_network_error(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            with patch("mid.update_checker.should_check", return_value=True):
                with patch("mid.update_checker.fetch_latest_version", return_value=None):
                    fake_stderr = StringIO()
                    fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                    with patch.object(sys, "stderr", fake_stderr):
                        # Should not raise, should not print
                        check_and_notify()
                        assert fake_stderr.getvalue() == ""
                        # Should still write cache with checked_at
                        cache = _read_cache()
                        assert cache is not None
                        assert "checked_at" in cache

    def test_never_raises(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            with patch("mid.update_checker.should_check", side_effect=RuntimeError("boom")):
                # Should not raise
                check_and_notify()
            with patch("mid.update_checker.should_check", return_value=True):
                with patch("mid.update_checker.fetch_latest_version", side_effect=RuntimeError("boom")):
                    fake_stderr = StringIO()
                    fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                    with patch.object(sys, "stderr", fake_stderr):
                        check_and_notify()  # should not raise
            with patch("mid.update_checker.should_check", return_value=True):
                with patch("mid.update_checker._write_cache", side_effect=OSError("disk full")):
                    with patch("mid.update_checker.fetch_latest_version", return_value="9.9.9"):
                        fake_stderr = StringIO()
                        fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                        with patch.object(sys, "stderr", fake_stderr):
                            # Even if write fails, banner should still print and not raise
                            real_import = __import__

                            def fake_import(name, *args, **kwargs):
                                if name.startswith("rich"):
                                    raise ImportError("no rich")
                                return real_import(name, *args, **kwargs)

                            with patch("builtins.__import__", side_effect=fake_import):
                                check_and_notify()

    def test_banner_to_stderr_only(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            with patch("mid.update_checker.should_check", return_value=True):
                with patch("mid.update_checker.fetch_latest_version", return_value="9.9.9"):
                    fake_stderr = StringIO()
                    fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                    fake_stdout = StringIO()
                    with patch.object(sys, "stderr", fake_stderr):
                        with patch.object(sys, "stdout", fake_stdout):
                            real_import = __import__

                            def fake_import(name, *args, **kwargs):
                                if name.startswith("rich"):
                                    raise ImportError("no rich")
                                return real_import(name, *args, **kwargs)

                            with patch("builtins.__import__", side_effect=fake_import):
                                check_and_notify()
                                assert "Update available" in fake_stderr.getvalue()
                                assert fake_stdout.getvalue() == ""

    def test_windows_banner_variant(self, tmp_path: Path, monkeypatch) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            with patch("mid.update_checker.should_check", return_value=True):
                with patch("mid.update_checker.fetch_latest_version", return_value="9.9.9"):
                    fake_stderr = StringIO()
                    fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                    with patch.object(sys, "stderr", fake_stderr):
                        with patch.object(sys, "platform", "win32"):
                            real_import = __import__

                            def fake_import(name, *args, **kwargs):
                                if name.startswith("rich"):
                                    raise ImportError("no rich")
                                return real_import(name, *args, **kwargs)

                            with patch("builtins.__import__", side_effect=fake_import):
                                check_and_notify()
                                assert "irm" in fake_stderr.getvalue()
                                assert "install.ps1" in fake_stderr.getvalue()

    def test_corrupt_cache_not_crash(self, tmp_path: Path) -> None:
        import types

        mock_dir = str(tmp_path / "cache")
        mod = types.ModuleType("platformdirs")
        mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"platformdirs": mod}):
            p = get_cache_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("corrupt", encoding="utf-8")
            with patch("mid.update_checker.should_check", return_value=True):
                with patch("mid.update_checker.fetch_latest_version", return_value="9.9.9"):
                    fake_stderr = StringIO()
                    fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                    with patch.object(sys, "stderr", fake_stderr):
                        real_import = __import__

                        def fake_import(name, *args, **kwargs):
                            if name.startswith("rich"):
                                raise ImportError("no rich")
                            return real_import(name, *args, **kwargs)

                        with patch("builtins.__import__", side_effect=fake_import):
                            # Should not raise, should fetch and print
                            check_and_notify()
                            assert "9.9.9" in fake_stderr.getvalue()


# ---------------------------------------------------------------------------
# Integration: main() preserves exit codes
# ---------------------------------------------------------------------------


class TestMainIntegration:
    def test_exit_codes_preserved(self, tmp_path: Path, monkeypatch) -> None:
        # Mock checker to ensure it doesn't interfere
        with patch("mid.update_checker.check_and_notify") as mock_check:
            # 0 success via --list-formats
            code, out, err = _run(["--list-formats"])
            assert code == 0
            assert mock_check.called

            mock_check.reset_mock()
            # 2 arg error: missing file
            code, out, err = _run(["convert", "nonexistent.docx"])
            assert code == 2
            assert mock_check.called

            mock_check.reset_mock()
            # 3 unsupported format
            src = tmp_path / "image.png"
            src.write_text("fake", encoding="utf-8")
            code, out, err = _run(["convert", str(src)])
            assert code == 3
            assert mock_check.called

            mock_check.reset_mock()
            # 1 conversion failure
            src2 = tmp_path / "broken.docx"
            src2.write_text("garbage", encoding="utf-8")
            with patch("markitdown.MarkItDown") as MockMD:
                inst = MockMD.return_value
                inst.convert.side_effect = RuntimeError("corrupt")
                code, out, err = _run(["convert", str(src2)])
                assert code == 1
                assert mock_check.called

    def test_main_banner_suppressed_in_non_tty(self, tmp_path: Path, monkeypatch) -> None:
        # _run uses StringIO which is not tty, so banner should be suppressed
        # Even if fetch would return newer, no banner should appear in err beyond normal error
        with patch("mid.update_checker.fetch_latest_version", return_value="9.9.9"):
            code, out, err = _run(["--list-formats"])
            assert "Update available" not in err
            assert "Update available" not in out

    def test_banner_not_on_help_or_version(self, tmp_path: Path) -> None:
        with patch("mid.update_checker.fetch_latest_version", return_value="9.9.9"):
            # Even with mocked newer version, help/version should not show banner because should_check false due to --help in sys.argv
            # But _run's redirect makes isatty false, so already suppressed. Need to test with isatty true but flags present
            # So we patch isatty True and then call _run; _run's redirect will override isatty? Need to directly test check_and_notify via main's finally?
            # Instead test that main with --help doesn't call fetch
            with patch("mid.update_checker.should_check", return_value=False):
                code, out, err = _run(["--help"])
                # should_check should have been called and returned False, but we mocked to False, so fetch not called
                # Instead test real should_check logic: patch isatty True and env, then call main with --help and ensure fetch not called
                pass
            # Directly test that should_check would be false for --help, so no banner
            with patch.object(sys.stderr, "isatty", return_value=True):
                # Need to simulate main's call to check_and_notify with sys.argv containing --help
                # We'll patch fetch to fail if called, and ensure no banner
                import types

                mock_dir = str(tmp_path / "cache")
                mod = types.ModuleType("platformdirs")
                mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
                with patch.dict(sys.modules, {"platformdirs": mod}):
                    with patch("mid.update_checker.fetch_latest_version") as mock_fetch:
                        old = sys.argv
                        sys.argv = ["mid", "--help"]
                        fake_stderr = StringIO()
                        fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                        out2 = StringIO()
                        try:
                            with redirect_stdout(out2), redirect_stderr(fake_stderr):
                                # Need to patch sys.stderr inside redirect? The redirect will replace sys.stderr with fake_stderr's wrapper?
                                # Simpler: just call check_and_notify directly with argv containing --help
                                # Actually check_and_notify uses sys.argv via should_check, so we can test directly
                                check_and_notify()
                                mock_fetch.assert_not_called()
                                assert "Update available" not in fake_stderr.getvalue()
                        finally:
                            sys.argv = old

    def test_checker_exception_does_not_change_exit_code(self, tmp_path: Path) -> None:
        with patch("mid.update_checker.check_and_notify", side_effect=RuntimeError("boom")):
            code, out, err = _run(["--list-formats"])
            assert code == 0
            # Should not have crashed
            assert "Supported:" in out

        with patch("mid.update_checker.check_and_notify", side_effect=RuntimeError("boom")):
            src = tmp_path / "missing.docx"
            # file not found -> exit 2, but checker exception should not change it
            code, out, err = _run(["convert", str(src)])
            assert code == 2

    def test_json_suppresses_banner_even_with_newer(self, tmp_path: Path) -> None:
        src = tmp_path / "test.docx"
        src.write_text("", encoding="utf-8")
        with patch("markitdown.MarkItDown") as MockMD:
            inst = MockMD.return_value
            inst.convert.return_value.text_content = "# Hello"
            # Mock newer version but --json should suppress
            with patch("mid.update_checker.fetch_latest_version", return_value="9.9.9"):
                with patch.object(sys.stderr, "isatty", return_value=True):
                    # _run will use StringIO (non-tty) so banner suppressed anyway; we need to test via direct check_and_notify with --json argv
                    # So we test should_check directly
                    assert should_check(argv=["mid", "convert", str(src), "--json"]) is False
                    # And via main: ensure no banner in stderr when using --json (even if we mock isatty true, _run's stderr is StringIO not tty, so we test via manual patch)
                    import types

                    mock_dir = str(tmp_path / "cache2")
                    mod = types.ModuleType("platformdirs")
                    mod.user_cache_dir = lambda appname: mock_dir  # type: ignore[attr-defined]
                    with patch.dict(sys.modules, {"platformdirs": mod}):
                        old_argv = sys.argv
                        sys.argv = ["mid", "convert", str(src), "--json"]
                        fake_stderr = StringIO()
                        fake_stderr.isatty = lambda: True  # type: ignore[attr-defined]
                        fake_stdout = StringIO()
                        try:
                            with patch.object(sys, "stderr", fake_stderr):
                                with patch.object(sys, "stdout", fake_stdout):
                                    with patch("mid.update_checker.fetch_latest_version", return_value="9.9.9"):
                                        # Need to ensure main's finally calls check_and_notify which will see --json
                                        # We'll call _run style but with patched isatty
                                        # Instead directly call check_and_notify and ensure no banner
                                        check_and_notify()
                                        assert "Update available" not in fake_stderr.getvalue()
                        finally:
                            sys.argv = old_argv
