"""Integration tests for engine facades — strict TDD.

Covers ARCH-07..11, LEGACY-08: explicit wins, ambiguity, delegates, Adapter, REGISTRY 7.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from mid.backends.base import Availability, Backend
from mid.backends.registry import registry
from mid.backends.adapter import BackendAdapter
from mid.engine import REGISTRY, convert_file, get_backend, list_backends, resolve_backend
from mid.models import ConvertResult


class FakeBackend(Backend):
    def __init__(self, name="fake", exts=None, available=True, reason=None):
        super().__init__()
        self.name = name
        self.display_name = name
        self.supported_extensions = frozenset(exts or {".doc"})
        self.required_tools = tuple()
        self._available = available
        self._reason = reason
        self.convert_calls = 0

    def probe(self) -> Availability:
        return Availability(
            available=self._available,
            version="1.0",
            tool_path="/bin/fake",
            reason=self._reason,
            checked_at=datetime.now(timezone.utc),
        )

    def convert(self, path: Path) -> ConvertResult:
        self.convert_calls += 1
        return ConvertResult(content=f"from {self.name}", metadata={"source": path.name}, success=True, error=None)


@pytest.fixture(autouse=True)
def clean_registry():
    # save original state, clear, yield, restore
    original = list(registry.list_all())
    registry.clear()
    yield
    registry.clear()
    for b in original:
        try:
            registry.register(b)
        except ValueError:
            pass


class TestEngineFacades:
    def test_list_get_deterministic(self):
        a = FakeBackend(name="a", exts={".doc"})
        b = FakeBackend(name="b", exts={".doc"})
        registry.register(a)
        registry.register(b)
        assert [x.name for x in list_backends()] == ["a", "b"]
        assert get_backend("a") is a
        assert get_backend("missing") is None

    def test_resolve_explicit_wins(self):
        a = FakeBackend(name="a", exts={".doc"})
        b = FakeBackend(name="b", exts={".doc"})
        registry.register(a)
        registry.register(b)
        # preferred b should win
        result = resolve_backend(".doc", preferred="b")
        assert result is b
        # preferred a
        assert resolve_backend(".doc", preferred="a") is a

    def test_resolve_ambiguity_requires_explicit(self):
        a = FakeBackend(name="a", exts={".doc"})
        b = FakeBackend(name="b", exts={".doc"})
        registry.register(a)
        registry.register(b)
        # without preferred and multiple candidates -> None (ambiguity)
        assert resolve_backend(".doc", preferred=None) is None
        # single candidate should resolve
        registry.clear()
        registry.register(a)
        assert resolve_backend(".doc", preferred=None) is a

    def test_resolve_no_candidates_none(self):
        assert resolve_backend(".unknown", preferred=None) is None

    def test_resolve_unknown_preferred_none(self):
        a = FakeBackend(name="a", exts={".doc"})
        registry.register(a)
        assert resolve_backend(".doc", preferred="ghost") is None


class TestConvertFileBackend:
    def test_backward_compatible_no_backend(self, tmp_path: Path):
        # without backend arg, delegates to existing REGISTRY (docx -> MarkitDown, doc -> LegacyPlaceholder)
        # For doc, should return legacy error with success False
        src = tmp_path / "sample.doc"
        src.write_text("x", encoding="utf-8")
        result = convert_file(src)
        assert result.success is False
        assert "legacy" in (result.error or "").lower()

        # For docx with mocked MarkitDown, success
        src2 = tmp_path / "file.docx"
        src2.write_text("x", encoding="utf-8")
        with patch("markitdown.MarkItDown") as MockMD:
            MockMD.return_value.convert.return_value.text_content = "# ok"
            result2 = convert_file(src2)
            assert result2.success is True

    def test_convert_with_backend_delegates(self, tmp_path: Path):
        b = FakeBackend(name="fake", exts={".doc"})
        registry.register(b)
        src = tmp_path / "in.doc"
        src.write_text("x", encoding="utf-8")
        result = convert_file(src, backend="fake")
        assert result.success is True
        assert "from fake" in result.content
        assert b.convert_calls == 1

    def test_unknown_backend_never_raises(self, tmp_path: Path):
        src = tmp_path / "a.doc"
        src.write_text("x", encoding="utf-8")
        result = convert_file(src, backend="ghost")
        assert result.success is False
        assert "unknown backend" in (result.error or "").lower()
        assert "ghost" in (result.error or "")

    def test_unavailable_maps_to_reason(self, tmp_path: Path):
        b = FakeBackend(name="soffice", exts={".doc"}, available=False, reason="soffice not found")
        registry.register(b)
        src = tmp_path / "a.doc"
        src.write_text("x", encoding="utf-8")
        result = convert_file(src, backend="soffice")
        assert result.success is False
        assert "soffice not found" in (result.error or "")

    def test_registry_still_7(self):
        # REGISTRY must still hold 7 entries
        assert len(REGISTRY) == 7
        assert ".docx" in REGISTRY
        assert ".doc" in REGISTRY

    def test_adapter_never_raise_via_engine(self, tmp_path: Path):
        class BadBackend(Backend):
            def __init__(self):
                super().__init__()
                self.name = "bad"
                self.display_name = "bad"
                self.supported_extensions = frozenset({".doc"})
                self.required_tools = tuple()

            def probe(self) -> Availability:
                return Availability(
                    available=True, version="1", tool_path="/bin/bad", reason=None, checked_at=datetime.now(timezone.utc)
                )

            def convert(self, path: Path) -> ConvertResult:
                raise RuntimeError("boom")

        b = BadBackend()
        registry.register(b)
        src = tmp_path / "a.doc"
        src.write_text("x", encoding="utf-8")
        # direct backend convert raises, but engine via convert_file should handle? Our engine delegates to b.convert which will raise, but convert_file wraps? Test expects never-raise via ConvertResult.
        # For BadBackend, convert_file should return success False not raise
        result = convert_file(src, backend="bad")
        # Our engine currently catches exception in convert_file and returns ConvertResult, so this should pass
        assert result.success is False
        assert "boom" in (result.error or "")


    def test_opt_in_backend_probed_on_explicit_selection(self, tmp_path: Path):
        class OptInFake(FakeBackend):
            def __init__(self):
                super().__init__(name="fake-office", available=False, reason="Office not detected")
                self.opt_in = True
                self.probe_calls = 0

            def probe(self) -> Availability:
                self.probe_calls += 1
                return super().probe()

        registry.register(OptInFake())
        src = tmp_path / "a.doc"
        src.write_text("x", encoding="utf-8")
        result = convert_file(src, backend="fake-office")
        assert result.success is False
        assert "Office not detected" in (result.error or "")
        assert "opt-in" not in (result.error or "").lower()
        assert registry.get("fake-office").probe_calls == 1


class TestAdapterIntegration:
    def test_adapter_maps_raise(self):
        class Raises(Backend):
            def __init__(self):
                super().__init__()
                self.name = "r"
                self.display_name = "r"
                self.supported_extensions = frozenset({".doc"})
                self.required_tools = tuple()

            def probe(self) -> Availability:
                return Availability(
                    available=True, version="1", tool_path="/bin/r", reason=None, checked_at=datetime.now(timezone.utc)
                )

            def convert(self, path: Path) -> ConvertResult:
                raise RuntimeError("fail")

        b = Raises()
        adapter = BackendAdapter(b)
        result = adapter.convert(Path("x.doc"))
        assert result.success is False
