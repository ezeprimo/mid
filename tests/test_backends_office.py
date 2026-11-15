"""Unit tests for OfficeBackend — strict TDD for OFFICE-01..06.

Scope: Word/Excel/PowerPoint (.doc/.xls/.ppt) via per-app DispatchEx (#41).
PowerPoint is single-instance, so the backend refuses an instance that already
has open presentations (exit 3, never Quit/kill) — S4.

Kill scope (maintainer decision): PID-scoped via GetWindowThreadProcessId.
taskkill /IM constrained to the allowlisted Office exes is fallback only.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def win32():
    """Pretend to run on Windows without touching the real platform."""
    with patch.object(sys, "platform", "win32"):
        yield


@pytest.fixture
def com_stub(monkeypatch):
    """Stub win32com.client so lazy imports succeed on Linux."""
    fake = MagicMock(name="win32com.client")
    monkeypatch.setitem(sys.modules, "win32com", MagicMock(name="win32com"))
    monkeypatch.setitem(sys.modules, "win32com.client", fake)
    return fake


def _backend():
    from mid.backends.office import OfficeBackend

    return OfficeBackend()


# --- 2.1 RED: killer argv ----------------------------------------------------

# Task 2.1 RED — killer uses list argv, shell=False, exe from allowlist only.


def test_killer_argv_pid_scoped():
    """Default killer is PID-scoped: list argv, shell=False, no user path."""
    from mid.backends.office import _default_killer

    with patch("mid.backends.office.subprocess.run") as mock_run:
        _default_killer(1234)
        assert mock_run.call_count == 1
        argv = mock_run.call_args[0][0]
        assert isinstance(argv, list)
        assert argv == ["taskkill", "/F", "/PID", "1234"]
        kwargs = mock_run.call_args.kwargs
        assert kwargs.get("shell") is False


def test_killer_argv_exe_allowlist_only(tmp_path):
    """Exe fallback is constrained to the allowlist; user paths never run."""
    from mid.backends.office import _ALLOWED_EXES, _default_killer

    assert _ALLOWED_EXES == frozenset({"WINWORD.EXE", "EXCEL.EXE", "POWERPNT.EXE"})
    evil = str(tmp_path / "evil.exe")
    with patch.dict(os.environ, {"MID_OFFICE_PATH": evil}):
        with patch("mid.backends.office.subprocess.run") as mock_run:
            _default_killer("WINWORD.EXE")
            argv = mock_run.call_args[0][0]
            assert isinstance(argv, list)
            assert kwargs_shell_false(mock_run)
            assert "WINWORD.EXE" in argv
            assert evil not in argv
            mock_run.reset_mock()
            # user-controlled path is never executed, even if requested
            _default_killer(evil)
            assert mock_run.call_count == 0
            _default_killer("outlook.exe")
            assert mock_run.call_count == 0


def kwargs_shell_false(mock_run):
    return mock_run.call_args.kwargs.get("shell") is False


# --- 2.2 RED: hang cleanup ---------------------------------------------------

# Task 2.2 RED — hung COM asserts Quit-called + killer-called + tmp removed.


def test_hang_cleanup_quit_kill_tmp(tmp_path):
    """Hung conversion: Quit called, killer called, mid-office- tmp removed."""
    import mid.backends.office as office_mod

    src = tmp_path / "in.doc"
    src.write_text("x", encoding="utf-8")

    block = threading.Event()
    app = MagicMock(name="WordApp")

    def fake_factory(progid):
        assert progid == "Word.Application"
        return app

    def hanging_saveas(html_path, *args, **kwargs):
        block.wait(timeout=30)

    docs = MagicMock()
    app.Documents.Open.return_value = docs
    docs.SaveAs.side_effect = hanging_saveas

    killer_calls = []
    before = {p.name for p in Path(tempfile.gettempdir()).iterdir() if p.name.startswith("mid-office-")}

    with patch.object(sys, "platform", "win32"):
        with patch.dict(os.environ, {"MID_OFFICE_TIMEOUT": "5"}):
            with patch.object(office_mod, "_COM_FACTORY", fake_factory):
                with patch.object(office_mod, "_KILLER", killer_calls.append):
                    b = office_mod.OfficeBackend()
                    result = b.convert(src)

    assert result.success is False
    assert "timed out" in (result.error or "").lower()
    assert app.Quit.called, "Quit must be called on hang"
    assert len(killer_calls) == 1, "kill fallback must run on hang"
    after = {p.name for p in Path(tempfile.gettempdir()).iterdir() if p.name.startswith("mid-office-")}
    assert after - before == set(), "mid-office- tmp must be removed even on timeout"


# --- 2.3 RED: bad-path fallthrough -------------------------------------------

# Task 2.3 RED — invalid MID_OFFICE_PATH falls through to App Paths.


def test_bad_path_fallthrough(win32, com_stub, tmp_path):
    """Invalid MID_OFFICE_PATH falls through to App Paths resolution."""
    from mid.backends import office as office_mod

    app_paths_exe = tmp_path / "WINWORD.EXE"
    app_paths_exe.write_text("x")
    with patch.dict(os.environ, {"MID_OFFICE_PATH": "/nonexistent/office.exe"}):
        with patch.object(office_mod, "_read_app_paths", return_value=app_paths_exe) as mock_app:
            with patch.object(office_mod, "_read_curver", return_value="16.0"):
                avail = office_mod.OfficeBackend().probe()
                assert mock_app.called, "bad env path must fall through to App Paths"
                assert avail.available is True
                assert avail.tool_path == str(app_paths_exe)


# --- OFFICE-01: identity ------------------------------------------------------


def test_office_identity_word_excel_powerpoint():
    """Scope is .doc/.xls/.ppt — one per-app COM server each (#41)."""
    from mid.backends.office import PROGIDS, OfficeBackend

    assert OfficeBackend.name == "office"
    assert OfficeBackend.opt_in is True
    assert OfficeBackend.supported_extensions == frozenset({".doc", ".xls", ".ppt"})
    assert set(PROGIDS) == {".doc", ".xls", ".ppt"}
    assert PROGIDS[".doc"] == ("Word.Application", "WINWORD.EXE", 12)
    assert PROGIDS[".xls"] == ("Excel.Application", "EXCEL.EXE", 51)
    assert PROGIDS[".ppt"] == ("PowerPoint.Application", "POWERPNT.EXE", 24)
    assert OfficeBackend.required_tools == ("WINWORD.EXE", "EXCEL.EXE", "POWERPNT.EXE")
    assert ".pptx" not in OfficeBackend.supported_extensions, "native MarkItDown handles .pptx"
    assert ".pps" not in OfficeBackend.supported_extensions


def test_office_registration_win32_only(win32, com_stub):
    """Guarded registration: win32-only, ValueError-safe, absent on Linux."""
    from mid.backends.registry import BackendRegistry

    reg = BackendRegistry()
    with patch.object(sys, "platform", "linux"):
        import importlib

        import mid.backends.office as office_mod

        importlib.reload(office_mod)
        assert reg.get("office") is None
    # win32 path registers without raising on duplicates
    from mid.backends.office import OfficeBackend

    reg.register(OfficeBackend())
    try:
        reg.register(OfficeBackend())
        raise AssertionError("duplicate registration must raise")
    except ValueError:
        pass


def test_office_absent_on_linux():
    """On Linux the win32 guard keeps office out of the shared registry."""
    from mid.backends.registry import registry

    names = [b.name for b in registry.list_all()]
    if sys.platform != "win32":
        assert "office" not in names
    else:
        pytest.skip("win32 runner registers office by design")


# --- OFFICE-02: probe ----------------------------------------------------------


def test_probe_platform_gate():
    """Non-win32 probe is unavailable with unsupported-platform reason."""
    with patch.object(sys, "platform", "linux"):
        avail = _backend().probe()
        assert avail.available is False
        assert "unsupported platform" in (avail.reason or "").lower()


def test_probe_env_precedence_valid(win32, com_stub, tmp_path):
    from mid.backends import office as office_mod

    fake = tmp_path / "WINWORD.EXE"
    fake.write_text("x")
    with patch.dict(os.environ, {"MID_OFFICE_PATH": str(fake)}):
        with patch.object(office_mod, "_read_curver", return_value="16.0"):
            avail = office_mod.OfficeBackend().probe()
            assert avail.available is True
            assert avail.tool_path == str(fake)
            assert avail.version == "16.0"


def test_probe_needs_win32com(win32, tmp_path):
    """Missing pywin32 maps to unavailable, never raises."""
    from mid.backends import office as office_mod

    fake = tmp_path / "WINWORD.EXE"
    fake.write_text("x")
    with patch.dict(os.environ, {"MID_OFFICE_PATH": str(fake)}):
        with patch.dict(sys.modules, {"win32com": None, "win32com.client": None}):
            sys.modules.pop("win32com.client", None)
            sys.modules.pop("win32com", None)
            with patch.object(office_mod, "_read_curver", return_value=None):
                # force ImportError by blocking the import machinery
                import builtins

                real_import = builtins.__import__

                def fake_import(name, *args, **kwargs):
                    if name.startswith("win32com"):
                        raise ImportError("No module named win32com")
                    return real_import(name, *args, **kwargs)

                with patch.object(builtins, "__import__", fake_import):
                    avail = office_mod.OfficeBackend().probe()
                    assert avail.available is False
                    assert "pywin32" in (avail.reason or "").lower()


def _probe_without_pywin32(office_mod, fake, monkeypatch):
    """Run probe with win32com import blocked; returns Availability."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("win32com"):
            raise ImportError("No module named win32com")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    return office_mod.OfficeBackend().probe()


def test_probe_missing_pywin32_source_names_extra(win32, tmp_path, monkeypatch):
    """Source checkout without pywin32 names the runnable pip fix."""
    from mid.backends import office as office_mod

    fake = tmp_path / "WINWORD.EXE"
    fake.write_text("x")
    monkeypatch.setenv("MID_OFFICE_PATH", str(fake))
    monkeypatch.delattr(sys, "frozen", raising=False)
    with patch.object(office_mod, "_read_curver", return_value=None):
        avail = _probe_without_pywin32(office_mod, fake, monkeypatch)
        assert avail.available is False
        reason = (avail.reason or "").lower()
        assert "pywin32" in reason
        assert "office-windows" in reason


def test_probe_missing_pywin32_frozen_names_binary_path(win32, tmp_path, monkeypatch):
    """Frozen binary without pywin32 names the binary situation, not the old fix."""
    from mid.backends import office as office_mod

    fake = tmp_path / "WINWORD.EXE"
    fake.write_text("x")
    monkeypatch.setenv("MID_OFFICE_PATH", str(fake))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with patch.object(office_mod, "_read_curver", return_value=None):
        avail = _probe_without_pywin32(office_mod, fake, monkeypatch)
        assert avail.available is False
        reason = (avail.reason or "").lower()
        assert "pywin32" in reason
        assert "binary" in reason
        assert "libreoffice" in reason
        assert "install the office-windows extra" not in reason


def test_probe_never_raises(win32):
    from mid.backends import office as office_mod

    with patch.object(office_mod, "_resolve_tool_path", side_effect=RuntimeError("boom")):
        avail = office_mod.OfficeBackend().probe()
        assert avail.available is False
        assert "boom" in (avail.reason or "")


# --- OFFICE-02/04: timeout clamp ----------------------------------------------


def test_resolve_timeout_clamp():
    from mid.backends.office import _resolve_timeout

    with patch.dict(os.environ, {}, clear=True):
        assert _resolve_timeout() == 30
    with patch.dict(os.environ, {"MID_OFFICE_TIMEOUT": "abc"}):
        assert _resolve_timeout() == 30
    with patch.dict(os.environ, {"MID_OFFICE_TIMEOUT": "1"}):
        assert _resolve_timeout() == 5
    with patch.dict(os.environ, {"MID_OFFICE_TIMEOUT": "9999"}):
        assert _resolve_timeout() == 300
    with patch.dict(os.environ, {"MID_OFFICE_TIMEOUT": "60"}):
        assert _resolve_timeout() == 60


# --- OFFICE-03: explicit selection + ambiguity ---------------------------------


def test_explicit_office_selection_and_ambiguity(win32, com_stub, tmp_path):
    """backend='office' selects Office; backend=None with 2 claimants -> None."""
    from mid.backends import office as office_mod
    from mid.engine import resolve_backend

    office = office_mod.OfficeBackend()
    other = MagicMock()
    other.name = "libreoffice"
    other.supported_extensions = frozenset({".doc"})

    from mid.backends.registry import registry

    original = list(registry.list_all())
    registry.clear()
    try:
        registry.register(office)
        registry.register(other)
        assert resolve_backend(".doc", preferred="office") is office
        # ambiguity: no preference, two claimants -> None (select-one)
        assert resolve_backend(".doc") is None
    finally:
        registry.clear()
        for b in original:
            try:
                registry.register(b)
            except ValueError:
                pass


def test_unknown_backend_exits_2(tmp_path, capsys):
    """CLI maps unknown backend to exit 2."""
    import sys as _sys

    from mid.backends.registry import registry

    original = list(registry.list_all())
    registry.clear()
    try:
        f = tmp_path / "sample.doc"
        f.write_text("x", encoding="utf-8")
        from mid.cli import main

        with patch.object(_sys, "argv", ["mid", "convert", str(f), "--backend", "office"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "unknown backend" in err.lower()
    finally:
        registry.clear()
        for b in original:
            try:
                registry.register(b)
            except ValueError:
                pass


def test_unavailable_stub_backend_exits_3(tmp_path, capsys):
    """CLI maps an unavailable backend to exit 3 — deterministic, no Office needed (#30)."""
    import sys as _sys
    from datetime import datetime, timezone

    from mid.backends.base import Availability, Backend
    from mid.backends.registry import registry
    from mid.models import ConvertResult

    class UnavailableStub(Backend):
        def __init__(self):
            super().__init__()
            self.name = "stub-office"
            self.display_name = "stub-office"
            self.supported_extensions = frozenset({".doc"})
            self.required_tools = tuple()

        def probe(self) -> Availability:
            return Availability(
                available=False,
                version=None,
                tool_path=None,
                reason="Office not detected",
                checked_at=datetime.now(timezone.utc),
            )

        def convert(self, path: Path) -> ConvertResult:
            raise AssertionError("must not convert when unavailable")

    original = list(registry.list_all())
    registry.clear()
    try:
        f = tmp_path / "sample.doc"
        f.write_text("x", encoding="utf-8")
        registry.register(UnavailableStub())
        from mid.cli import main

        with patch.object(_sys, "argv", ["mid", "convert", str(f), "--backend", "stub-office"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 3
        err = capsys.readouterr().err
        assert "unavailable" in err.lower()
    finally:
        registry.clear()
        for b in original:
            try:
                registry.register(b)
            except ValueError:
                pass


def test_office_absent_reports_unavailable_exit_3(tmp_path, capsys):
    """Real backend: exit 3 only when Office is actually absent (#30)."""
    import sys as _sys

    from mid.backends import office as office_mod
    from mid.backends.registry import registry

    if office_mod.OfficeBackend().probe().available:
        pytest.skip("Office present on this runner — absent-path not applicable")
    original = list(registry.list_all())
    registry.clear()
    try:
        f = tmp_path / "sample.doc"
        f.write_text("x", encoding="utf-8")
        registry.register(office_mod.OfficeBackend())
        from mid.cli import main

        with patch.object(_sys, "argv", ["mid", "convert", str(f), "--backend", "office"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 3
        err = capsys.readouterr().err
        assert "unavailable" in err.lower()
    finally:
        registry.clear()
        for b in original:
            try:
                registry.register(b)
            except ValueError:
                pass


def test_office_present_passes_availability_gate(tmp_path, capsys):
    """Real backend: when Office is present, explicit selection passes the gate (#30)."""
    import sys as _sys

    from mid.backends import office as office_mod
    from mid.backends.registry import registry

    if not office_mod.OfficeBackend().probe().available:
        pytest.skip("Office absent on this runner — gate test not applicable")
    original = list(registry.list_all())
    registry.clear()
    try:
        f = tmp_path / "sample.doc"
        f.write_text("x", encoding="utf-8")
        registry.register(office_mod.OfficeBackend())
        from mid.cli import main

        # A dummy .doc may or may not convert, but it must NOT exit 3:
        # availability was established by the probe above.
        try:
            with patch.object(_sys, "argv", ["mid", "convert", str(f), "--backend", "office"]):
                main()
        except SystemExit as exc:
            assert exc.code != 3
    finally:
        registry.clear()
        for b in original:
            try:
                registry.register(b)
            except ValueError:
                pass


# --- OFFICE-04: convert boundary -----------------------------------------------


def _fake_word_app(allow):
    app = MagicMock(name="FakeWord")
    docs = MagicMock()
    app.Documents.Open.return_value = docs

    def _saveas(out_path, *args, **kwargs):
        from docx import Document

        doc = Document()
        doc.add_paragraph("hello")
        doc.save(str(out_path))

    docs.SaveAs.side_effect = _saveas
    allow.append((app, docs))
    return app


def _fake_excel_app(allow):
    app = MagicMock(name="FakeExcel")
    wb = MagicMock()
    app.Workbooks.Open.return_value = wb

    def _saveas(out_path, *args, **kwargs):
        from openpyxl import Workbook

        book = Workbook()
        book.active.title = "Data"
        book.active["A1"] = "hello"
        book.save(str(out_path))

    wb.SaveAs.side_effect = _saveas
    allow.append((app, wb))
    return app


def _fake_com_success(progid, allow):
    """Per-app shaped double: Word progid -> Documents, Excel progid -> Workbooks."""
    if "Excel" in progid:
        return _fake_excel_app(allow)
    return _fake_word_app(allow)


def test_convert_hardened_open_and_cleanup(tmp_path):
    """Convert opens hidden/read-only with guards off; Close+Quit in finally."""
    import mid.backends.office as office_mod

    src = tmp_path / "in.doc"
    src.write_text("x", encoding="utf-8")
    seen = []
    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod, "_COM_FACTORY", lambda progid: _fake_com_success(progid, seen)):
            with patch.object(office_mod, "_KILLER", MagicMock()) as mock_killer:
                mock_md = MagicMock()
                mock_md.convert.return_value = MagicMock(success=True, content="# hello", error=None)
                with patch("mid.converters.markitdown.MarkitDownConverter", return_value=mock_md):
                    result = office_mod.OfficeBackend().convert(src)
    assert result.success is True
    assert "# hello" in result.content
    app, docs = seen[0]
    assert app.Visible is False
    assert app.DisplayAlerts == 0
    app.Documents.Open.assert_called_once()
    open_kwargs = app.Documents.Open.call_args.kwargs
    assert open_kwargs.get("ReadOnly") is True
    assert "WithWindow" not in open_kwargs, "Documents.Open has no WithWindow param (Word 2013 rejects it, #28)"
    assert docs.SaveAs.call_count == 1
    assert docs.SaveAs.call_args.kwargs.get("FileFormat") == 12
    assert str(docs.SaveAs.call_args[0][0]).endswith(".docx")
    assert app.Workbooks.Open.call_count == 0
    assert docs.Close.called
    assert app.Quit.called
    assert not mock_killer.called, "killer must not run on success"


def test_convert_excel_uses_workbooks_and_xlsx_format(tmp_path):
    """Excel .xls uses Workbooks.Open/Close and SaveAs FileFormat 51 (.xlsx)."""
    import mid.backends.office as office_mod

    src = tmp_path / "in.xls"
    src.write_text("x", encoding="utf-8")
    seen = []
    progids = []

    def factory(progid):
        progids.append(progid)
        return _fake_com_success(progid, seen)

    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod, "_COM_FACTORY", factory):
            with patch.object(office_mod, "_KILLER", MagicMock()):
                mock_md = MagicMock()
                mock_md.convert.return_value = MagicMock(success=True, content="# hello", error=None)
                with patch("mid.converters.markitdown.MarkitDownConverter", return_value=mock_md):
                    result = office_mod.OfficeBackend().convert(src)
    assert result.success is True
    assert progids == ["Excel.Application"]
    app, wb = seen[0]
    app.Workbooks.Open.assert_called_once()
    open_kwargs = app.Workbooks.Open.call_args.kwargs
    assert open_kwargs.get("ReadOnly") is True
    assert app.Documents.Open.call_count == 0
    assert wb.SaveAs.call_count == 1
    assert wb.SaveAs.call_args.kwargs.get("FileFormat") == 51
    assert str(wb.SaveAs.call_args[0][0]).endswith(".xlsx")
    assert wb.Close.call_count == 1
    close_args, close_kwargs = wb.Close.call_args
    assert (close_args and close_args[0] in (0, False)) or close_kwargs.get("SaveChanges") in (0, False)
    assert app.Quit.called


def test_convert_uses_mid_office_prefix_and_copies_input(tmp_path):
    """Tmp dir uses mid-office- prefix; input is copied in, never opened in place."""
    import mid.backends.office as office_mod

    src = tmp_path / "in.xls"
    src.write_text("x", encoding="utf-8")
    prefixes = []
    real_tmp = tempfile.TemporaryDirectory
    from unittest.mock import MagicMock as _MM

    def spy_tmp(*args, **kwargs):
        prefixes.append(kwargs.get("prefix"))
        return real_tmp(*args, **kwargs)

    seen = []
    with patch.object(sys, "platform", "win32"):
        with patch("tempfile.TemporaryDirectory", side_effect=spy_tmp):
            with patch.object(office_mod, "_COM_FACTORY", lambda progid: _fake_com_success(progid, seen)):
                mock_md = _MM()
                mock_md.convert.return_value = _MM(success=True, content="# ok", error=None)
                with patch("mid.converters.markitdown.MarkitDownConverter", return_value=mock_md):
                    with patch("shutil.copy2", wraps=__import__("shutil").copy2) as mock_copy:
                        result = office_mod.OfficeBackend().convert(src)
    assert result.success is True
    assert prefixes and all(p == "mid-office-" for p in prefixes)
    assert mock_copy.called


def test_convert_unsupported_and_missing():
    b = _backend()
    r = b.convert(Path("/nonexistent/x.doc"))
    assert r.success is False
    assert "file not found" in (r.error or "").lower()


# --- PowerPoint (.ppt) COM branch (#41) ---------------------------------------


class _FakePresentation:
    """Double for a PowerPoint ``Presentation`` returned by ``Presentations.Open``."""

    def __init__(self) -> None:
        self.saveas_calls: list[tuple] = []
        self.close_calls = 0

    def SaveAs(self, filename, *args, **kwargs):
        self.saveas_calls.append((str(filename), args, kwargs))
        Path(filename).write_bytes(b"PK\x03\x04")

    def Close(self, *args, **kwargs):
        self.close_calls += 1


class _FakePresentations:
    """Double for ``PowerPoint.Application.Presentations`` — records every call."""

    def __init__(self, open_count: int = 0) -> None:
        self.Count = open_count
        self.open_calls: list[tuple] = []
        self.opened: list[_FakePresentation] = []

    def Open(self, filename, *args, **kwargs):
        self.open_calls.append((str(filename), args, kwargs))
        pres = _FakePresentation()
        self.opened.append(pres)
        return pres


class _FakePowerPointApp:
    """PowerPoint.Application double that fails loudly on ``ActivePresentation``."""

    def __init__(self, open_count: int = 0) -> None:
        self.Presentations = _FakePresentations(open_count)
        self.quit_calls = 0

    def Quit(self) -> None:
        self.quit_calls += 1

    @property
    def ActivePresentation(self):
        raise AssertionError("app.ActivePresentation must never be accessed — WithWindow=False leaves no active presentation")


def _saveas_format(call: tuple):
    """Effective FileFormat of a recorded SaveAs call (positional or keyword)."""
    _, args, kwargs = call
    if "FileFormat" in kwargs:
        return kwargs["FileFormat"]
    return args[0] if args else None


def test_convert_ppt_uses_powerpoint_com(tmp_path):
    """`.ppt` goes DispatchEx -> windowless Open -> SaveAs 24 (.pptx) -> Close -> Quit."""
    import mid.backends.office as office_mod

    src = tmp_path / "deck.ppt"
    src.write_text("x", encoding="utf-8")
    app = _FakePowerPointApp(open_count=0)
    progids: list[str] = []

    def factory(progid):
        progids.append(progid)
        return app

    killer = MagicMock()
    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod, "_COM_FACTORY", factory):
            with patch.object(office_mod, "_KILLER", killer):
                mock_md = MagicMock()
                mock_md.convert.return_value = MagicMock(success=True, content="# Slide 1", error=None)
                with patch("mid.converters.markitdown.MarkitDownConverter", return_value=mock_md):
                    result = office_mod.OfficeBackend().convert(src)

    assert result.success is True
    assert result.exit_code is None
    assert "# Slide 1" in result.content
    assert progids == ["PowerPoint.Application"]
    presentations = app.Presentations
    assert len(presentations.open_calls) == 1, "Presentations.Open must run exactly once"
    _, open_args, open_kwargs = presentations.open_calls[0]
    assert open_args == () or all(a in (True, False, 0) for a in open_args)
    assert open_kwargs.get("ReadOnly") is True
    assert not open_kwargs.get("WithWindow"), "WithWindow=False is what makes this safe (no active presentation)"
    assert not open_kwargs.get("Untitled")
    pres = presentations.opened[0]
    assert len(pres.saveas_calls) == 1
    target = pres.saveas_calls[0][0]
    assert target.endswith(".pptx"), "SaveAs 24 writes a .pptx MarkItDown can read"
    assert _saveas_format(pres.saveas_calls[0]) == 24
    assert pres.close_calls == 1
    assert app.quit_calls == 1, "an instance that was empty when taken is mid's own — Quit is allowed"
    assert not killer.called
    assert Path(mock_md.convert.call_args[0][0]).suffix == ".pptx"


def test_convert_ppt_shared_instance_aborts_with_exit_3(tmp_path):
    """S4: a PowerPoint instance with open presentations is never touched."""
    import mid.backends.office as office_mod

    src = tmp_path / "deck.ppt"
    src.write_text("x", encoding="utf-8")
    app = _FakePowerPointApp(open_count=1)
    killer = MagicMock()
    md_factory = MagicMock()

    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod, "_COM_FACTORY", lambda progid: app):
            with patch.object(office_mod, "_KILLER", killer):
                with patch("mid.converters.markitdown.MarkitDownConverter", md_factory):
                    result = office_mod.OfficeBackend().convert(src)

    assert result.success is False
    assert result.content == ""
    assert result.exit_code == 3, "shared-instance abort maps to exit 3 (S4/D6)"
    # Nothing was opened, saved, closed, quit or killed.
    assert app.Presentations.open_calls == []
    assert app.Presentations.opened == []
    assert app.quit_calls == 0, "Quit is forbidden on an instance mid did not start"
    assert not killer.called, "the PID killer is forbidden on a shared instance"
    assert not md_factory.called
    err = (result.error or "").lower()
    assert "powerpoint" in err
    assert "1 open presentation" in err
    assert "--backend libreoffice" in err
    assert "single-instance" in err


def test_intermediate_format_constants():
    """OOXML intermediate: .doc -> docx/12, .xls -> xlsx/51, .ppt -> pptx/24."""
    from mid.backends.office import _INTERMEDIATE_EXT, PROGIDS

    assert PROGIDS[".doc"] == ("Word.Application", "WINWORD.EXE", 12)
    assert PROGIDS[".xls"] == ("Excel.Application", "EXCEL.EXE", 51)
    assert PROGIDS[".ppt"] == ("PowerPoint.Application", "POWERPNT.EXE", 24)
    assert _INTERMEDIATE_EXT == {".doc": ".docx", ".xls": ".xlsx", ".ppt": ".pptx"}


def test_html_helpers_removed():
    """HTML-intermediate helpers are dead code after the OOXML switch."""
    import mid.backends.office as office_mod

    for name in (
        "_decode_html_bytes",
        "_detect_charset",
        "_resolve_frameset_sheets",
        "_normalize_meta_charset",
        "_clean_word_html",
    ):
        assert not hasattr(office_mod, name), f"{name} must be removed"


def test_convert_20mb_cap_on_intermediate(tmp_path):
    import mid.backends.office as office_mod

    src = tmp_path / "in.doc"
    src.write_text("x", encoding="utf-8")

    def big_factory(progid):
        app = MagicMock()

        def _saveas(out_path, *args, **kwargs):
            Path(out_path).write_bytes(b"x" * 100)

        docs = MagicMock()
        app.Documents.Open.return_value = docs
        docs.SaveAs.side_effect = _saveas
        return app

    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod, "_COM_FACTORY", big_factory):
            with patch("mid.backends.office._MAX_OUTPUT_BYTES", 10):
                r = office_mod.OfficeBackend().convert(src)
                assert r.success is False
                assert "20 MB" in (r.error or "") or "exceeds" in (r.error or "").lower()


def test_convert_delegates_ooxml_path_to_markitdown(tmp_path):
    """The OOXML intermediate path (not HTML) reaches MarkItDown."""
    import mid.backends.office as office_mod

    src = tmp_path / "in.doc"
    src.write_text("x", encoding="utf-8")
    seen = []
    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod, "_COM_FACTORY", lambda progid: _fake_com_success(progid, seen)):
            mock_md = MagicMock()
            mock_md.convert.return_value = MagicMock(success=True, content="# ok", error=None)
            with patch("mid.converters.markitdown.MarkitDownConverter", return_value=mock_md):
                r = office_mod.OfficeBackend().convert(src)
    assert r.success is True
    delegated = Path(mock_md.convert.call_args[0][0])
    assert delegated.suffix == ".docx"
    assert delegated.name == "in.docx"


def test_convert_multisheet_xlsx_all_sheets(tmp_path):
    """End-to-end with the REAL MarkItDown reader: every sheet converts.

    The fake COM layer writes a genuine 3-sheet .xlsx (as Excel SaveAs 51
    would); the backend must delegate it untouched so MarkItDown emits one
    ``## <name>`` section per sheet — no per-sheet join needed.
    """
    import mid.backends.office as office_mod

    src = tmp_path / "in.xls"
    src.write_text("x", encoding="utf-8")
    sheet_names = ["VersionHistory", "LibroBanco", "CUT"]

    def multisheet_factory(progid):
        from openpyxl import Workbook

        app = MagicMock()

        def _saveas(out_path, *args, **kwargs):
            book = Workbook()
            book.active.title = sheet_names[0]
            book.active["A1"] = "version"
            for name in sheet_names[1:]:
                ws = book.create_sheet(name)
                ws["A1"] = f"content-{name}"
            book.save(str(out_path))

        wb = MagicMock()
        app.Workbooks.Open.return_value = wb
        wb.SaveAs.side_effect = _saveas
        return app

    with patch.object(sys, "platform", "win32"):
        with patch("shutil.which", return_value=None):
            with patch.object(office_mod, "_COM_FACTORY", multisheet_factory):
                r = office_mod.OfficeBackend().convert(src)
    assert r.success is True
    for name in sheet_names:
        assert name in r.content, f"sheet {name} missing from output"
    assert r.content.count("## ") >= 3
    assert "content-LibroBanco" in r.content
    assert "content-CUT" in r.content


def test_convert_docx_end_to_end_real_markitdown(tmp_path):
    """End-to-end with the REAL MarkItDown reader: docx text flows through."""
    import mid.backends.office as office_mod

    src = tmp_path / "in.doc"
    src.write_text("x", encoding="utf-8")

    def rich_doc_factory(progid):
        from docx import Document

        app = MagicMock()

        def _saveas(out_path, *args, **kwargs):
            doc = Document()
            doc.add_heading("Objetivo", level=1)
            doc.add_paragraph("texto con ryas")
            doc.save(str(out_path))

        docs = MagicMock()
        app.Documents.Open.return_value = docs
        docs.SaveAs.side_effect = _saveas
        return app

    with patch.object(sys, "platform", "win32"):
        with patch("shutil.which", return_value=None):
            with patch.object(office_mod, "_COM_FACTORY", rich_doc_factory):
                r = office_mod.OfficeBackend().convert(src)
    assert r.success is True
    assert "Objetivo" in r.content
    assert "texto con ryas" in r.content
    assert "supportLists" not in r.content
    assert "\u00a0" not in r.content


def test_copy_exclusive_lock_maps_to_file_locked(tmp_path):
    """Exclusive lock on the pre-COM copy maps to file-locked, locale-independent (#BUG-2)."""
    import mid.backends.office as office_mod

    src = tmp_path / "in.xls"
    src.write_text("x", encoding="utf-8")

    def locked_copy(*args, **kwargs):
        exc = OSError("[WinError 32] El proceso no tiene acceso al archivo porque está siendo utilizado por otro proceso")
        exc.winerror = 32
        raise exc

    with patch.object(sys, "platform", "win32"):
        with patch("shutil.copy2", side_effect=locked_copy):
            with patch.object(office_mod, "_KILLER", MagicMock()) as mock_killer:
                r = office_mod.OfficeBackend().convert(src)
    assert r.success is False
    assert "file locked" in (r.error or "").lower()
    assert not mock_killer.called


def test_map_error_winerror_codes():
    """Numeric WinError codes map locale-independently (Spanish messages included)."""
    from mid.backends.office import _map_error

    for code in (32, 33):
        exc = OSError("cualquier mensaje localizado")
        exc.winerror = code
        assert "file locked" in _map_error(exc).lower()
    denied = OSError("Acceso denegado.")
    denied.winerror = 5
    assert "permission denied" in _map_error(denied).lower()


def test_convert_releases_app_reference_deterministically(tmp_path):
    """convert() must not retain the COM app wrapper after return (#29 no-orphan)."""
    import gc as _gc
    import weakref

    import mid.backends.office as office_mod

    src = tmp_path / "in.doc"
    src.write_text("x", encoding="utf-8")
    refs = []

    class Doc:
        def SaveAs(self, html_path, **kwargs):
            Path(html_path).write_text("<html><body>hi</body></html>", encoding="utf-8")

        def Close(self, *args):
            pass

    class Docs:
        def Open(self, *args, **kwargs):
            return Doc()

    class FakeApp:
        def __init__(self):
            self.Documents = Docs()

        def Quit(self):
            pass

    def factory(progid):
        app = FakeApp()
        refs.append(weakref.ref(app))
        return app

    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod, "_COM_FACTORY", factory):
            mock_md = MagicMock()
            mock_md.convert.return_value = MagicMock(success=True, content="# hi", error=None)
            with patch("mid.converters.markitdown.MarkitDownConverter", return_value=mock_md):
                r = office_mod.OfficeBackend().convert(src)
    assert r.success is True
    _gc.collect()
    assert refs[0]() is None, "COM app wrapper retained after convert() — orphan risk (#29)"


# --- OFFICE-05: error taxonomy --------------------------------------------------


def test_error_taxonomy_never_raises(tmp_path):
    """Locked/busy/orphan failures map to ConvertResult, never raise."""
    import mid.backends.office as office_mod

    src = tmp_path / "in.doc"
    src.write_text("x", encoding="utf-8")

    def locked_factory(progid):
        raise OSError("locked for editing by another user")

    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod, "_COM_FACTORY", locked_factory):
            r = office_mod.OfficeBackend().convert(src)
            assert r.success is False
            assert "close office" in (r.error or "").lower()

    def busy_factory(progid):
        raise RuntimeError("RPC_E_SERVERCALL_RETRYLATER call rejected")

    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod, "_COM_FACTORY", busy_factory):
            r2 = office_mod.OfficeBackend().convert(src)
            assert r2.success is False
            assert "busy" in (r2.error or "").lower() and "retry" in (r2.error or "").lower()


def test_convert_on_linux_reports_platform(tmp_path):
    """Linux convert short-circuits with unsupported-platform, never raises."""
    with patch.object(sys, "platform", "linux"):
        p = tmp_path / "a.doc"
        p.write_text("x", encoding="utf-8")
        r = _backend().convert(p)
        assert r.success is False
        assert "unsupported platform" in (r.error or "").lower()


# --- OOXML markdown normalization (NBSP + NaN + Unnamed) ------------------------


def test_normalize_nbsp_to_space_and_collapse():
    """Literal U+00A0 becomes a regular space; runs collapse, newlines kept."""
    from mid.backends.office import _normalize_ooxml_markdown

    out = _normalize_ooxml_markdown("a  b\nc  d")
    assert " " not in out
    assert out == "a b\nc d"


def test_normalize_whole_cell_nan_only():
    """Whole-cell NaN empties; words containing 'nan' (financiero) survive."""
    from mid.backends.office import _normalize_ooxml_markdown

    table = "| a | NaN | financiero |\n|---|---|---|\n| nan | NAN | medio de pago |"
    out = _normalize_ooxml_markdown(table)
    assert "financiero" in out
    assert "medio de pago" in out
    assert "NaN" not in out and "nan" not in out.replace("financiero", "")
    # column count stable: every row keeps 3 cells
    for line in out.splitlines():
        assert line.count("|") == 4
    # prose NaN without pipes is untouched
    assert _normalize_ooxml_markdown("NaN values indicate gaps") == "NaN values indicate gaps"


def test_normalize_unnamed_header_keeps_columns():
    """Exact 'Unnamed: N' headers blank; pipe count (columns) unchanged."""
    from mid.backends.office import _normalize_ooxml_markdown

    header = "| Unnamed: 0 | Name | Unnamed: 12 |"
    out = _normalize_ooxml_markdown(header)
    assert "Unnamed" not in out
    assert out.count("|") == header.count("|")
    # real header text is never blanked
    assert _normalize_ooxml_markdown("| Renamed: 3 | Name |") == "| Renamed: 3 | Name |"


def test_normalize_never_raises():
    """Normalizer is total: empty input passes through, never raises."""
    from mid.backends.office import _normalize_ooxml_markdown

    assert _normalize_ooxml_markdown("") == ""
    assert isinstance(_normalize_ooxml_markdown("| a | NaN |\n"), str)


# --- Merged-cell forward-fill (AI legibility) -------------------------------------


def _make_merged_fixture(path: Path) -> Path:
    """Matriz-like sheet: merged header zone + vertical merges + spacer row."""
    from openpyxl import Workbook

    book = Workbook()
    ws = book.active
    ws.title = "Banco"
    ws["A1"] = "Transición"
    ws.merge_cells("A1:A2")  # vertical header merge
    ws["B1"] = "Condiciones"
    ws.merge_cells("B1:C1")  # horizontal header merge
    ws["D1"] = "Impactos"
    ws.merge_cells("D1:E1")  # horizontal header merge
    ws["B2"] = "Cond 1"
    ws["C2"] = "Cond n"
    ws["D2"] = "Código"
    ws["E2"] = "Tipo"
    ws["A3"] = "Confirmar"
    ws.merge_cells("A3:A4")  # vertical body merge
    ws["B3"] = "x1"
    ws["C3"] = "y1"
    ws["D3"] = "m1"
    ws["E3"] = "t1"
    ws["B4"] = "x2"
    ws["C4"] = "y2"
    ws["D4"] = "m2"
    # E4 genuinely empty (never merged) — must NOT be filled.
    # Row 5 all-empty spacer row (never merged) — must stay empty.
    ws["A6"] = "Otro"
    ws["B6"] = "z"
    book.save(str(path))
    return path


def test_expand_merged_cells_horizontal_and_vertical(tmp_path):
    """2x2-style merges fill both axes; real empties stay empty."""
    from openpyxl import load_workbook

    from mid.backends.office import _expand_merged_cells

    p = _make_merged_fixture(tmp_path / "m.xlsx")
    assert _expand_merged_cells(p) is None
    ws = load_workbook(p)["Banco"]
    assert list(ws.merged_cells.ranges) == []
    # vertical fills
    assert ws["A2"].value == "Transición"
    assert ws["A4"].value == "Confirmar"
    # horizontal fills
    assert ws["C1"].value == "Condiciones"
    assert ws["E1"].value == "Impactos"
    # genuine empties untouched: spacer row + never-merged E4
    assert ws["A5"].value is None and ws["C5"].value is None
    assert ws["E4"].value is None


def test_expand_merged_cells_never_raises(tmp_path):
    """Missing file and missing openpyxl both fall back silently."""
    import builtins

    from mid.backends import office as office_mod

    assert office_mod._expand_merged_cells(tmp_path / "missing.xlsx") is None
    p = _make_merged_fixture(tmp_path / "m.xlsx")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openpyxl":
            raise ImportError("No module named openpyxl")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", fake_import):
        assert office_mod._expand_merged_cells(p) is None
    # fallback left the merges untouched
    from openpyxl import load_workbook

    assert len(list(load_workbook(p)["Banco"].merged_cells.ranges)) == 4


def test_convert_xls_merged_headers_forward_filled(tmp_path):
    """End-to-end with the REAL MarkItDown reader: merged fixture has no gaps.

    The fake COM layer copies a merged xlsx as the intermediate (as Excel
    SaveAs 51 preserving merges would); every output row must be
    self-contained while the spacer row stays empty.
    """
    import re

    import mid.backends.office as office_mod

    src = tmp_path / "in.xls"
    src.write_text("x", encoding="utf-8")
    fixture = _make_merged_fixture(tmp_path / "fixture.xlsx")

    def merged_factory(progid):
        import shutil

        app = MagicMock()

        def _saveas(out_path, *args, **kwargs):
            shutil.copy2(fixture, out_path)

        wb = MagicMock()
        app.Workbooks.Open.return_value = wb
        wb.SaveAs.side_effect = _saveas
        return app

    with patch.object(sys, "platform", "win32"):
        with patch("shutil.which", return_value=None):
            with patch.object(office_mod, "_COM_FACTORY", merged_factory):
                r = office_mod.OfficeBackend().convert(src)
    assert r.success is True
    assert "Unnamed" not in r.content
    assert not re.search(r"(?<=\|)\s*nan\s*(?=\|)", r.content, re.IGNORECASE)
    # forward-filled values repeat on every row they span
    assert r.content.count("Transición") >= 2
    assert r.content.count("Confirmar") >= 2
    # header row has no empty cells (pandas dedupes repeats as Name.1)
    header = next(line for line in r.content.splitlines() if "Condiciones" in line and "Cond 1" not in line)
    assert "||" not in header.replace(" ", "")
    # spacer row stays an all-empty separator, never filled with prior values
    assert any(re.fullmatch(r"[|\s]+", line) and line.count("|") >= 6 for line in r.content.splitlines())


# --- Exit-code plumbing for the shared-instance guard (S4/D6) -------------------


def _office_available():
    """Availability payload for a Windows host with Office installed."""
    from datetime import datetime, timezone

    from mid.backends.base import Availability

    return Availability(
        available=True,
        version="15.0",
        tool_path="C:/Office/POWERPNT.EXE",
        reason=None,
        checked_at=datetime.now(timezone.utc),
    )


def _run_cli(argv: list[str]):
    """Invoke ``mid`` with *argv*; return the exit code (``None`` when no exit)."""
    import sys as _sys

    from mid.cli import main

    with patch.object(_sys, "argv", ["mid", *argv]):
        try:
            main()
        except SystemExit as exc:
            return exc.code
    return None


def _with_office_backend(office_mod):
    """Register a probed-available office backend and yield the shared registry."""
    import contextlib

    from mid.backends.registry import registry

    @contextlib.contextmanager
    def _swap():
        original = list(registry.list_all())
        registry.clear()
        registry.register(office_mod.OfficeBackend())
        try:
            yield registry
        finally:
            registry.clear()
            for b in original:
                try:
                    registry.register(b)
                except ValueError:
                    pass

    return _swap()


def test_cli_ppt_shared_instance_exits_3(tmp_path, capsys):
    """`mid convert --backend office deck.ppt` exits 3 for the shared-instance guard."""
    import mid.backends.office as office_mod

    src = tmp_path / "deck.ppt"
    src.write_text("x", encoding="utf-8")
    app = _FakePowerPointApp(open_count=2)

    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod.OfficeBackend, "probe", return_value=_office_available()):
            with patch.object(office_mod, "_COM_FACTORY", lambda progid: app):
                with patch.object(office_mod, "_KILLER", MagicMock()):
                    with _with_office_backend(office_mod):
                        code = _run_cli(["convert", str(src), "--backend", "office"])

    assert code == 3
    err = capsys.readouterr().err.lower()
    assert "powerpoint" in err
    assert "2 open presentations" in err
    assert "--backend libreoffice" in err
    assert app.quit_calls == 0
    assert app.Presentations.open_calls == []


def test_cli_ordinary_conversion_failure_still_exits_1(tmp_path, capsys):
    """The exit-code mapping is narrow: every other conversion failure stays exit 1."""
    import mid.backends.office as office_mod

    src = tmp_path / "deck.ppt"
    src.write_text("x", encoding="utf-8")

    def broken_factory(progid):
        raise OSError("locked for editing by another user")

    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod.OfficeBackend, "probe", return_value=_office_available()):
            with patch.object(office_mod, "_COM_FACTORY", broken_factory):
                with _with_office_backend(office_mod):
                    code = _run_cli(["convert", str(src), "--backend", "office"])

    assert code == 1, "a plain conversion failure must not inherit exit 3"
    err = capsys.readouterr().err.lower()
    assert "conversion failed" in err
    assert "close office" in err


def test_batch_ppt_shared_instance_counts_failed_and_exits_1(tmp_path, capsys):
    """`batch` keeps its contract: the file fails and the run exits 1 (never 3)."""
    import mid.backends.office as office_mod

    in_dir = tmp_path / "in"
    in_dir.mkdir()
    (in_dir / "deck.ppt").write_text("x", encoding="utf-8")
    out_dir = tmp_path / "out"
    app = _FakePowerPointApp(open_count=1)

    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod.OfficeBackend, "probe", return_value=_office_available()):
            with patch.object(office_mod, "_COM_FACTORY", lambda progid: app):
                with patch.object(office_mod, "_KILLER", MagicMock()):
                    with _with_office_backend(office_mod):
                        code = _run_cli(["batch", str(in_dir), "-o", str(out_dir), "--backend", "office"])

    assert code == 1
    captured = capsys.readouterr()
    assert "Processed: 1, Succeeded: 0, Failed: 1" in captured.out
    assert "deck.ppt" in captured.err
    assert "PowerPoint" in captured.err
    assert not list(out_dir.glob("*.md")), "nothing may be written for a refused deck"
    assert app.quit_calls == 0
    assert app.Presentations.open_calls == []


def test_ppt_dispatch_hang_never_kills_powerpoint_processes(tmp_path, monkeypatch):
    """S4: a hang before the guard must never reach the kill-all fallback."""
    import time
    import mid.backends.office as office_mod

    monkeypatch.setenv("MID_OFFICE_TIMEOUT", "1")
    src = tmp_path / "deck.ppt"
    src.write_text("x", encoding="utf-8")
    calls: list = []

    def hanging_factory(progid):
        # Deliberately far above the clamped timeout floor (MID_OFFICE_TIMEOUT
        # "1" resolves to 5s): a 5s sleep raced the 5s join and sometimes
        # finished first, which made this assertion time-dependent.
        time.sleep(30)
        raise AssertionError("unreachable")

    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod, "_COM_FACTORY", hanging_factory):
            with patch.object(office_mod, "_KILLER", lambda t: calls.append(t)):
                result = office_mod.OfficeBackend().convert(src)

    assert result.success is False and result.exit_code is None
    assert "timed out" in (result.error or "")
    assert calls == [], f"a shared-capable PowerPoint instance must never be killed (got {calls})"


def test_ppt_count_read_hang_keeps_may_quit_false(tmp_path, monkeypatch):
    """S4: may_quit stays False while the count probe is still running; nothing is killed.

    The probe must outlive the clamped timeout by a wide margin, otherwise the
    race decides the assertion: MID_OFFICE_TIMEOUT clamps up to 5s, so a 5s sleep
    can finish first, the guard then correctly observes an empty instance and the
    kill becomes legitimate. 30s keeps the probe unambiguously pending.
    """
    import time
    import mid.backends.office as office_mod

    monkeypatch.setenv("MID_OFFICE_TIMEOUT", "1")

    class _SlowPresentations:
        @property
        def Count(self):
            time.sleep(30)
            return 0

    class _App:
        Presentations = _SlowPresentations()

    src = tmp_path / "deck.ppt"
    src.write_text("x", encoding="utf-8")
    calls: list = []
    with patch.object(sys, "platform", "win32"):
        with patch.object(office_mod, "_COM_FACTORY", lambda progid: _App()):
            with patch.object(office_mod, "_KILLER", lambda t: calls.append(t)):
                result = office_mod.OfficeBackend().convert(src)

    assert result.success is False
    assert calls == []


# --- OFFICE-06: integration gate -------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows + installed Office")
def test_real_doc_conversion_win32(tmp_path):
    """Real .doc -> md on a licensed Windows runner (skipped on Linux)."""
    from mid.backends.office import OfficeBackend

    b = OfficeBackend()
    avail = b.probe()
    if not avail.available:
        pytest.skip(f"Office not detected on this runner: {avail.reason}")
    src = tmp_path / "sample.doc"
    src.write_bytes(b"placeholder")
    result = b.convert(src)
    assert result.success
    assert result.content.strip()


def _create_real_ppt(path: Path) -> None:
    """Create a genuine legacy ``.ppt`` via PowerPoint COM (ppSaveAsPresentation = 1)."""
    import gc

    import pythoncom
    from win32com.client import DispatchEx

    pythoncom.CoInitialize()
    app = None
    pres = None
    slide = None
    owns = False
    try:
        app = DispatchEx("PowerPoint.Application")
        if int(app.Presentations.Count) > 0:
            raise RuntimeError("a PowerPoint instance with open presentations is running")
        owns = True
        pres = app.Presentations.Add()
        slide = pres.Slides.Add(1, 2)  # 2 = ppLayoutText (title + body)
        slide.Shapes.Title.TextFrame.TextRange.Text = "Titulo de prueba 41"
        slide.Shapes.Placeholders(2).TextFrame.TextRange.Text = "Cuerpo de la diapositiva"
        pres.SaveAs(str(path), 1)  # 1 = ppSaveAsPresentation (.ppt)
    finally:
        # Release the presentation and its slide before Quit: wrappers released
        # after PowerPoint exited report RPC_E_DISCONNECTED from the finalizer.
        slide = None
        if pres is not None:
            try:
                pres.Close()
            except Exception:
                pass
        pres = None
        if owns and app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        app = None
        gc.collect()
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows + installed PowerPoint")
def test_real_ppt_conversion_win32(tmp_path):
    """Real .ppt -> md on a Windows host with PowerPoint (skipped elsewhere)."""
    from mid.backends.office import OfficeBackend

    b = OfficeBackend()
    avail = b.probe()
    if not avail.available:
        pytest.skip(f"Office not detected on this runner: {avail.reason}")
    src = tmp_path / "sample.ppt"
    try:
        _create_real_ppt(src)
    except Exception as exc:  # no PowerPoint COM / caption missing
        pytest.skip(f"could not create a real .ppt on this runner: {exc}")
    assert src.stat().st_size > 0
    result = b.convert(src)
    if result.exit_code == 3:
        pytest.skip(f"refused to touch a live PowerPoint instance: {result.error}")
    assert result.success, result.error
    assert result.content.strip()
    assert "Titulo de prueba 41" in result.content
