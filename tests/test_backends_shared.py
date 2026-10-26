"""Tests for the shared backend env/probe helpers (issue #47).

Both backends duplicated the same two shapes: an env-var path override that must
be an existing file and falls through when invalid, and a timeout clamped to a
range with a default. These tests pin the extracted contract before the
backends delegate to it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mid.backends import _env


class TestResolveTimeout:
    def test_default_when_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("MID_X_TIMEOUT", raising=False)

        assert _env.resolve_timeout("MID_X_TIMEOUT", "x") == 30

    @pytest.mark.parametrize("raw", ["abc", "", "1.5", "many"])
    def test_invalid_falls_back_to_default(self, monkeypatch, raw: str) -> None:
        monkeypatch.setenv("MID_X_TIMEOUT", raw)

        assert _env.resolve_timeout("MID_X_TIMEOUT", "x") == 30

    def test_below_minimum_clamps_up(self, monkeypatch) -> None:
        monkeypatch.setenv("MID_X_TIMEOUT", "4")

        assert _env.resolve_timeout("MID_X_TIMEOUT", "x") == 5

    def test_above_maximum_clamps_down(self, monkeypatch) -> None:
        monkeypatch.setenv("MID_X_TIMEOUT", "301")

        assert _env.resolve_timeout("MID_X_TIMEOUT", "x") == 300

    @pytest.mark.parametrize("raw,expected", [("5", 5), ("42", 42), ("300", 300)])
    def test_in_range_value_is_used(self, monkeypatch, raw: str, expected: int) -> None:
        monkeypatch.setenv("MID_X_TIMEOUT", raw)

        assert _env.resolve_timeout("MID_X_TIMEOUT", "x") == expected

    def test_bounds_and_default_are_parameters_not_constants(self, monkeypatch) -> None:
        monkeypatch.delenv("MID_X_TIMEOUT", raising=False)
        assert _env.resolve_timeout("MID_X_TIMEOUT", "x", default=90) == 90

        monkeypatch.setenv("MID_X_TIMEOUT", "0")
        assert _env.resolve_timeout("MID_X_TIMEOUT", "x", minimum=1, maximum=10) == 1

        monkeypatch.setenv("MID_X_TIMEOUT", "99")
        assert _env.resolve_timeout("MID_X_TIMEOUT", "x", minimum=1, maximum=10) == 10


class TestResolveEnvPath:
    def test_existing_file_wins_and_skips_the_chain(self, monkeypatch, tmp_path: Path) -> None:
        tool = tmp_path / "soffice"
        tool.write_text("", encoding="utf-8")
        monkeypatch.setenv("MID_X_PATH", str(tool))
        calls: list[str] = []

        path, hint = _env.resolve_env_path("MID_X_PATH", ("soffice",), lambda name: calls.append(name) or None, "not found")

        assert path == tool
        assert hint is None
        assert calls == []

    def test_invalid_env_falls_through_to_the_chain(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("MID_X_PATH", str(tmp_path / "missing"))
        found = tmp_path / "from-chain"

        path, hint = _env.resolve_env_path("MID_X_PATH", ("first", "second"), lambda name: found, "not found")

        assert path == found
        assert hint is None

    def test_directory_is_not_accepted_as_a_tool_path(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("MID_X_PATH", str(tmp_path))

        path, hint = _env.resolve_env_path("MID_X_PATH", ("soffice",), lambda name: None, "not found")

        assert path is None
        assert hint == "not found"

    def test_chain_returns_the_first_hit(self, monkeypatch) -> None:
        monkeypatch.delenv("MID_X_PATH", raising=False)
        seen: list[str] = []

        def finder(name: str):
            seen.append(name)
            return Path(f"/usr/bin/{name}") if name == "second" else None

        path, hint = _env.resolve_env_path("MID_X_PATH", ("first", "second", "third"), finder, "not found")

        assert path == Path("/usr/bin/second")
        assert hint is None
        assert seen == ["first", "second"]

    def test_no_hit_returns_the_hint(self, monkeypatch) -> None:
        monkeypatch.delenv("MID_X_PATH", raising=False)

        path, hint = _env.resolve_env_path("MID_X_PATH", ("a",), lambda name: None, "install the tool")

        assert path is None
        assert hint == "install the tool"


class TestBackendsDelegateToTheSharedHelpers:
    """The per-backend functions stay as the tested seam, delegating."""

    def test_libreoffice_timeout_matches_the_shared_helper(self, monkeypatch) -> None:
        from mid.backends import libreoffice

        for raw in ("15", "3", "999", "nope"):
            monkeypatch.setenv("MID_LIBREOFFICE_TIMEOUT", raw)
            assert libreoffice._resolve_timeout() == _env.resolve_timeout("MID_LIBREOFFICE_TIMEOUT", "libreoffice")

    def test_office_timeout_matches_the_shared_helper(self, monkeypatch) -> None:
        from mid.backends import office

        for raw in ("15", "3", "999", "nope"):
            monkeypatch.setenv("MID_OFFICE_TIMEOUT", raw)
            assert office._resolve_timeout() == _env.resolve_timeout("MID_OFFICE_TIMEOUT", "office")

    def test_libreoffice_env_precedence_is_preserved(self, monkeypatch, tmp_path: Path) -> None:
        from mid.backends import libreoffice

        tool = tmp_path / "soffice"
        tool.write_text("", encoding="utf-8")
        monkeypatch.setenv("MID_LIBREOFFICE_PATH", str(tool))

        assert libreoffice._resolve_tool_path() == (tool, None)

    def test_office_hint_is_preserved(self, monkeypatch) -> None:
        from mid.backends import office

        monkeypatch.delenv("MID_OFFICE_PATH", raising=False)
        monkeypatch.setattr(office, "_read_app_paths", lambda exe: None)

        path, hint = office._resolve_tool_path()

        assert path is None
        assert hint == "Office not detected — install Word/Excel 2016+ or set MID_OFFICE_PATH"
