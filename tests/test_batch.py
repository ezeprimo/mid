"""Tests for ``mid batch`` — file discovery, output structure, error handling."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
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
# Argument validation
# ===========================================================================


class TestBatchArgumentErrors:
    def test_no_input_dir(self) -> None:
        code, out, err = _run(["batch"])
        assert code == 2
        assert "INPUT_DIR" in err

    def test_input_not_a_directory(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("", encoding="utf-8")
        code, out, err = _run(["batch", str(f), "-o", str(tmp_path / "out")])
        assert code == 2
        assert "not a directory" in err.lower()

    def test_flatten_without_recursive(self, tmp_path: Path) -> None:
        d = tmp_path / "indir"
        d.mkdir()
        code, out, err = _run(["batch", str(d), "-o", str(tmp_path / "out"), "--flatten"])
        assert code == 2
        assert "--flatten requires --recursive" in err

    def test_preserve_without_recursive(self, tmp_path: Path) -> None:
        d = tmp_path / "indir"
        d.mkdir()
        code, out, err = _run(["batch", str(d), "-o", str(tmp_path / "out"), "--preserve"])
        assert code == 2
        assert "--preserve requires --recursive" in err

    def test_no_output_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "indir"
        d.mkdir()
        code, out, err = _run(["batch", str(d)])
        assert code == 2
        assert "--output" in err


# ===========================================================================
# Basic flat (non-recursive)
# ===========================================================================


class TestBatchBasic:
    def test_processes_supported_files_only(
        self,
        tmp_path: Path,
        sample_dir: Path,
        mock_convert_success,
    ) -> None:
        output = tmp_path / "out"
        code, out, err = _run(["batch", str(sample_dir), "-o", str(output)])

        assert code == 0
        assert (output / "a.md").exists()
        assert (output / "b.md").exists()
        assert not (output / "notes.md").exists()  # .txt skipped

    def test_summary_report(
        self,
        tmp_path: Path,
        sample_dir: Path,
        mock_convert_success,
    ) -> None:
        output = tmp_path / "out"
        code, out, err = _run(["batch", str(sample_dir), "-o", str(output)])

        assert "Processed: 2" in out
        assert "Succeeded: 2" in out
        assert "Failed: 0" in out
        assert "Skipped: 1" in out

    def test_ignores_subdirectories(
        self,
        tmp_path: Path,
        nested_dir: Path,
        mock_convert_success,
    ) -> None:
        output = tmp_path / "out"
        code, out, err = _run(["batch", str(nested_dir), "-o", str(output)])

        assert code == 0
        assert (output / "root.md").exists()
        assert not (output / "sub.md").exists()
        assert not (output / "sub" / "sub.md").exists()
        assert "Processed: 1" in out

    def test_output_dir_is_created(
        self,
        tmp_path: Path,
        sample_dir: Path,
        mock_convert_success,
    ) -> None:
        output = tmp_path / "new-dir" / "out"
        code, out, err = _run(["batch", str(sample_dir), "-o", str(output)])
        assert code == 0


# ===========================================================================
# JSON summary (issue #45)
# ===========================================================================

STAGE_KEYS = {"detection_ms", "probe_ms", "conversion_ms", "total_ms"}


class TestBatchJson:
    """`batch --json` emits a machine-readable summary on a pure stdout."""

    def test_emits_pure_json_document(
        self,
        tmp_path: Path,
        sample_dir: Path,
        mock_convert_success,
    ) -> None:
        output = tmp_path / "out"
        code, out, err = _run(["batch", str(sample_dir), "-o", str(output), "--json"])

        assert code == 0, f"stderr: {err}"
        payload = json.loads(out)  # stdout must be a single parsable document
        assert "Processed:" not in out

        assert payload["processed"] == 2
        assert payload["succeeded"] == 2
        assert payload["failed"] == 0
        assert payload["skipped"] == 1

        assert set(payload["timings"]) == {"total_ms", "worst_ms", "p50_ms"}
        for key, value in payload["timings"].items():
            assert isinstance(value, int), key
            assert value >= 0, key

        assert len(payload["files"]) == 2
        assert {entry["source"] for entry in payload["files"]} == {"a.docx", "b.pdf"}
        for entry in payload["files"]:
            assert set(entry) == {"source", "success", "error", "timings"}
            assert entry["success"] is True
            assert entry["error"] is None
            # An engine that reports no stage timings (mock or third party) must
            # degrade to zeros, never crash or omit the keys.
            assert set(entry["timings"]) == STAGE_KEYS
            assert all(isinstance(v, int) and v >= 0 for v in entry["timings"].values())

    def test_json_reports_failures_and_keeps_exit_code(
        self,
        tmp_path: Path,
        sample_dir: Path,
        mock_convert_failure,
    ) -> None:
        output = tmp_path / "out"
        code, out, err = _run(["batch", str(sample_dir), "-o", str(output), "--json"])

        assert code == 1, "batch keeps exiting 1 when a file fails, --json or not"
        payload = json.loads(out)
        assert payload["processed"] == 2
        assert payload["succeeded"] == 0
        assert payload["failed"] == 2
        for entry in payload["files"]:
            assert entry["success"] is False
            assert entry["error"]
        # Human-facing diagnostics still go to stderr, never into the document.
        assert "error:" in err

    def test_worst_and_p50_track_real_per_file_elapsed_time(
        self,
        tmp_path: Path,
        sample_dir: Path,
    ) -> None:
        delays = {"a.docx": 0.06, "b.pdf": 0.02}

        def fake_convert(path: Path, *, backend: str | None = None, availability: object = None) -> ConvertResult:
            time.sleep(delays[path.name])
            return ConvertResult(
                content="# Converted",
                metadata={"source": path.name, "format": path.suffix.lstrip("."), "success": True},
                success=True,
                error=None,
            )

        output = tmp_path / "out"
        with patch("mid.cli.convert_file", side_effect=fake_convert):
            code, out, _err = _run(["batch", str(sample_dir), "-o", str(output), "--json"])

        assert code == 0
        payload = json.loads(out)
        totals = {entry["source"]: entry["timings"]["total_ms"] for entry in payload["files"]}

        assert totals["a.docx"] > totals["b.pdf"], totals
        timings = payload["timings"]
        assert timings["worst_ms"] == max(totals.values())
        assert timings["worst_ms"] >= 55, timings
        assert min(totals.values()) <= timings["p50_ms"] <= max(totals.values())
        assert timings["total_ms"] >= timings["worst_ms"]


class TestBatchRecursivePreserve:
    def test_preserves_structure(
        self,
        tmp_path: Path,
        nested_dir: Path,
        mock_convert_success,
    ) -> None:
        output = tmp_path / "out"
        code, out, err = _run(
            [
                "batch",
                str(nested_dir),
                "-o",
                str(output),
                "--recursive",
                "--preserve",
            ]
        )
        assert code == 0
        assert (output / "root.md").exists()
        assert (output / "sub" / "sub.md").exists()
        assert (output / "sub" / "sub2" / "deep.md").exists()

    def test_summary_counts_all(
        self,
        tmp_path: Path,
        nested_dir: Path,
        mock_convert_success,
    ) -> None:
        output = tmp_path / "out"
        code, out, err = _run(
            [
                "batch",
                str(nested_dir),
                "-o",
                str(output),
                "--recursive",
                "--preserve",
            ]
        )
        assert "Processed: 3" in out
        assert "Succeeded: 3" in out


# ===========================================================================
# Recursive — flatten
# ===========================================================================


class TestBatchRecursiveFlatten:
    def test_flattens_structure(
        self,
        tmp_path: Path,
        nested_dir: Path,
        mock_convert_success,
    ) -> None:
        output = tmp_path / "out"
        code, out, err = _run(
            [
                "batch",
                str(nested_dir),
                "-o",
                str(output),
                "--recursive",
                "--flatten",
            ]
        )
        assert code == 0
        assert (output / "root.md").exists()
        assert (output / "sub.md").exists()
        assert (output / "deep.md").exists()

        # No subdirectories in output
        assert not (output / "sub").exists() or not (output / "sub").is_dir()

    def test_collision_uses_parent_prefix(
        self,
        tmp_path: Path,
        collision_dir: Path,
        mock_convert_success,
    ) -> None:
        output = tmp_path / "out"
        code, out, err = _run(
            [
                "batch",
                str(collision_dir),
                "-o",
                str(output),
                "--recursive",
                "--flatten",
            ]
        )
        assert code == 0

        # First report.docx from root → report.md
        assert (output / "report.md").exists()
        # Second report.docx from a/ → a-report.md
        assert (output / "a-report.md").exists()
        # report.xlsx from b/ → b-report.md (collision on "report")
        assert (output / "b-report.md").exists()

        # Total 3 files
        md_files = list(output.glob("*.md"))
        assert len(md_files) == 3

    def test_flatten_collision_with_pre_existing_output(
        self,
        tmp_path: Path,
        collision_dir: Path,
        mock_convert_success,
    ) -> None:
        """Pre-existing .md files in output should not break collision resolution."""
        output = tmp_path / "out"
        output.mkdir()
        # Pre-create a file that would collide
        (output / "report.md").write_text("preexisting", encoding="utf-8")

        code, out, err = _run(
            [
                "batch",
                str(collision_dir),
                "-o",
                str(output),
                "--recursive",
                "--flatten",
            ]
        )
        assert code == 0
        # report.md already exists from root — should get a-report.md from a/
        assert (output / "report.md").exists()
        # Either a-report.md or a-report-1.md depending on collision resolution
        assert (output / "a-report.md").exists() or (output / "a-report-1.md").exists()

    def test_deep_collisions_resolve_to_unique_names(
        self,
        tmp_path: Path,
        mock_convert_success,
    ) -> None:
        collision_dir = tmp_path / "collision-deep"
        collision_dir.mkdir()

        (collision_dir / "report.docx").write_text("root", encoding="utf-8")

        (collision_dir / "a" / "same").mkdir(parents=True)
        (collision_dir / "a" / "same" / "report.docx").write_text("a same", encoding="utf-8")

        (collision_dir / "b" / "same").mkdir(parents=True)
        (collision_dir / "b" / "same" / "report.docx").write_text("b same", encoding="utf-8")

        output = tmp_path / "out"
        code, out, err = _run(
            [
                "batch",
                str(collision_dir),
                "-o",
                str(output),
                "--recursive",
                "--flatten",
            ]
        )
        assert code == 0

        assert (output / "report.md").exists()
        assert (output / "a-same-report.md").exists()
        assert (output / "b-same-report.md").exists()

        md_files = sorted(p.name for p in output.glob("*.md"))
        assert md_files == ["a-same-report.md", "b-same-report.md", "report.md"]

    def test_flatten_collision_index_greater_than_one(
        self,
        tmp_path: Path,
        mock_convert_success,
    ) -> None:
        """Three files with same stem in same parent force collision_index > 1."""
        d = tmp_path / "collision-deep-index"
        d.mkdir()
        (d / "report.docx").write_text("report docx", encoding="utf-8")
        (d / "report.xlsx").write_text("report xlsx", encoding="utf-8")
        (d / "report.pptx").write_text("report pptx", encoding="utf-8")

        output = tmp_path / "out"
        code, out, err = _run(
            [
                "batch",
                str(d),
                "-o",
                str(output),
                "--recursive",
                "--flatten",
            ]
        )
        assert code == 0

        md_files = sorted(p.name for p in output.glob("*.md"))
        assert "report.md" in md_files
        assert len(md_files) == 3


# ===========================================================================
# Symlinks
# ===========================================================================


class TestBatchSymlinks:
    @pytest.mark.skipif(
        os.name == "nt" and not os.environ.get("MSYSTEM"),
        reason="symlink support unreliable on Windows without MSYS",
    )
    def test_symlink_to_supported_file_is_included(self, tmp_path: Path, mock_convert_success) -> None:
        """Symlink to a .docx should be processed in batch."""
        d = tmp_path / "input"
        d.mkdir()
        real_file = tmp_path / "real.docx"
        real_file.write_text("real", encoding="utf-8")
        link = d / "link.docx"
        link.symlink_to(real_file)

        output = tmp_path / "out"
        code, out, err = _run(["batch", str(d), "-o", str(output)])

        assert code == 0
        assert (output / "link.md").exists()


# ===========================================================================
# Non-fatal errors in batch
# ===========================================================================


class TestBatchNonFatal:
    def test_failure_continues_processing(
        self,
        tmp_path: Path,
        mock_convert_failure,
    ) -> None:
        d = tmp_path / "indir"
        d.mkdir()
        (d / "a.docx").write_text("", encoding="utf-8")
        (d / "b.docx").write_text("", encoding="utf-8")

        output = tmp_path / "out"
        code, out, err = _run(["batch", str(d), "-o", str(output)])

        assert code == 1  # non-zero when any file fails
        assert "Succeeded: 0" in out
        assert "Failed: 2" in out
        assert not (output / "a.md").exists()  # not written on failure


# ===========================================================================
# Real E2E batch
# ===========================================================================


class TestBatchRealE2E:
    """Real end-to-end batch conversion against generated .docx files."""

    def _require_markitdown(self) -> None:
        if importlib.util.find_spec("markitdown") is None:
            pytest.fail(
                "Real E2E tests require markitdown in local .venv. "
                "Install with: .venv\\Scripts\\python -m pip install 'markitdown[all]'",
            )

    def test_real_docx_batch_writes_markdown_and_reports_summary(
        self,
        tmp_path: Path,
        make_docx,
    ) -> None:
        self._require_markitdown()

        input_dir = tmp_path / "input"
        input_dir.mkdir()
        make_docx(input_dir / "first.docx", text="First batch e2e content")
        make_docx(input_dir / "second.docx", text="Second batch e2e content")
        (input_dir / "ignore.txt").write_text("skip", encoding="utf-8")

        output = tmp_path / "out"
        code, out, err = _run(["batch", str(input_dir), "-o", str(output)])

        assert code == 0
        assert err == ""

        first_md = output / "first.md"
        second_md = output / "second.md"
        assert first_md.exists()
        assert second_md.exists()
        assert "First batch e2e content" in first_md.read_text(encoding="utf-8")
        assert "Second batch e2e content" in second_md.read_text(encoding="utf-8")

        assert "Processed: 2" in out
        assert "Succeeded: 2" in out
        assert "Failed: 0" in out
        assert "Skipped: 1" in out


# ===========================================================================
# Edge cases
# ===========================================================================


class TestBatchEdgeCases:
    def test_empty_directory(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        output = tmp_path / "out"
        code, out, err = _run(["batch", str(d), "-o", str(output)])
        assert code == 0
        assert "Processed: 0" in out
        assert "Succeeded: 0" in out
        assert "Skipped: 0" in out

    def test_unsupported_only_directory(self, tmp_path: Path) -> None:
        d = tmp_path / "unsupported"
        d.mkdir()
        (d / "readme.txt").write_text("text", encoding="utf-8")
        (d / "image.png").write_text("png", encoding="utf-8")
        output = tmp_path / "out"
        code, out, err = _run(["batch", str(d), "-o", str(output)])
        assert code == 0
        assert "Processed: 0" in out
        assert "Skipped: 2" in out

    def test_output_path_is_existing_file(self, tmp_path: Path) -> None:
        d = tmp_path / "indir"
        d.mkdir()
        (d / "test.docx").write_text("", encoding="utf-8")
        existing_file = tmp_path / "out.txt"
        existing_file.write_text("", encoding="utf-8")
        code, out, err = _run(["batch", str(d), "-o", str(existing_file)])
        assert code == 2
        assert "not a directory" in err.lower()


class TestBatchNonRecursiveCollision:
    def test_non_recursive_collision_does_not_overwrite(self, tmp_path: Path, mock_convert_success) -> None:
        """Two files with same stem in non-recursive mode should not overwrite."""
        d = tmp_path / "indir"
        d.mkdir()
        (d / "report.docx").write_text("docx", encoding="utf-8")
        (d / "report.xlsx").write_text("xlsx", encoding="utf-8")
        output = tmp_path / "out"
        code, out, err = _run(["batch", str(d), "-o", str(output)])
        assert code == 0
        md_files = list(output.glob("*.md"))
        assert len(md_files) == 2  # Both preserved, no silent overwrite


class TestBatchWriteFailure:
    def test_write_failure_reported(self, tmp_path: Path, mock_convert_success) -> None:
        d = tmp_path / "indir"
        d.mkdir()
        (d / "test.docx").write_text("", encoding="utf-8")
        output = tmp_path / "out"

        from pathlib import Path as P
        from unittest.mock import patch as p

        with p.object(P, "write_text", side_effect=OSError("disk full")):
            code, out, err = _run(["batch", str(d), "-o", str(output)])

        assert code == 1
        assert "Failed: 1" in out


# ===========================================================================
# --backend (issue #40)
# ===========================================================================


class TestBatchBackend:
    """`batch --backend` mirrors `convert --backend` (issue #40)."""

    @pytest.fixture
    def fake_backend(self):
        """Register a backend that declares .odt and reports availability."""
        from datetime import datetime, timezone

        from mid.backends.base import Availability, Backend
        from mid.backends.registry import registry
        from mid.models import ConvertResult as _ConvertResult

        class _Fake(Backend):
            def __init__(self, available: bool, reason: str | None = None) -> None:
                super().__init__()
                self.name = "libreoffice"
                self.display_name = "LibreOffice"
                self.supported_extensions = frozenset({".odt", ".rtf"})
                self.required_tools = tuple()
                self._available = available
                self._reason = reason

            def probe(self) -> Availability:
                return Availability(
                    available=self._available,
                    version="7.6",
                    tool_path="/usr/bin/soffice",
                    reason=self._reason,
                    checked_at=datetime.now(timezone.utc),
                )

            def convert(self, path: Path) -> _ConvertResult:
                return _ConvertResult(content="from backend", metadata={}, success=True, error=None)

        original = list(registry.list_all())
        registry.clear()

        def register(available: bool = True, reason: str | None = None) -> _Fake:
            backend = _Fake(available=available, reason=reason)
            registry.register(backend)
            return backend

        yield register

        registry.clear()
        for backend in original:
            registry.register(backend)

    @pytest.fixture
    def mixed_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "mixed"
        d.mkdir()
        (d / "modern.docx").write_text("docx", encoding="utf-8")
        (d / "legacy.odt").write_text("odt", encoding="utf-8")
        (d / "notes.txt").write_text("skip", encoding="utf-8")
        return d

    def test_backend_converts_the_formats_it_declares(
        self, fake_backend, mixed_dir: Path, tmp_path: Path, mock_convert_success
    ) -> None:
        fake_backend(available=True)
        output = tmp_path / "out"

        code, out, err = _run(["batch", str(mixed_dir), "-o", str(output), "--backend", "libreoffice"])

        assert code == 0, f"stderr: {err}"
        # The backend declares .odt; .docx and .txt are not its job.
        assert (output / "legacy.md").exists()
        assert not (output / "modern.md").exists()
        assert "Processed: 1" in out
        assert "Skipped: 2" in out
        assert mock_convert_success.call_args.kwargs["backend"] == "libreoffice"

    def test_unknown_backend_exits_2_and_does_nothing(
        self, fake_backend, mixed_dir: Path, tmp_path: Path, mock_convert_success
    ) -> None:
        fake_backend(available=True)
        output = tmp_path / "out"

        code, out, err = _run(["batch", str(mixed_dir), "-o", str(output), "--backend", "nope"])

        assert code == 2
        assert "unknown backend 'nope'" in err
        assert not mock_convert_success.called
        assert not output.exists()

    def test_unavailable_backend_exits_3_and_does_nothing(
        self, fake_backend, mixed_dir: Path, tmp_path: Path, mock_convert_success
    ) -> None:
        fake_backend(available=False, reason="LibreOffice not found — install LibreOffice 7.6+")
        output = tmp_path / "out"

        code, out, err = _run(["batch", str(mixed_dir), "-o", str(output), "--backend", "libreoffice"])

        assert code == 3
        assert "libreoffice" in err
        assert "install LibreOffice 7.6+" in err
        assert not mock_convert_success.called
        assert not output.exists()

    def test_without_backend_backend_formats_are_still_skipped(
        self, fake_backend, mixed_dir: Path, tmp_path: Path, mock_convert_success
    ) -> None:
        fake_backend(available=True)
        output = tmp_path / "out"

        code, out, err = _run(["batch", str(mixed_dir), "-o", str(output)])

        assert code == 0
        assert (output / "modern.md").exists()
        assert not (output / "legacy.md").exists()
        # Auto-routing in batch is out of scope for #40: without the flag these
        # stay skipped rather than silently changing the count semantics.
        assert "Skipped: 2" in out


# ===========================================================================
# Single probe on `batch --backend` (issue #70)
# ===========================================================================


class CountingBatchBackend:
    """Probe-counting backend for the batch pre-flight (#70)."""

    def make(self, *, available: bool = True, reason: str | None = None):
        from datetime import datetime, timezone

        from mid.backends.base import Availability, Backend
        from mid.models import ConvertResult as _ConvertResult

        class _Counting(Backend):
            def __init__(self) -> None:
                super().__init__()
                self.name = "counting"
                self.display_name = "Counting"
                self.supported_extensions = frozenset({".odt"})
                self.required_tools = tuple()
                self.probe_calls = 0
                self.convert_calls: list[Path] = []

            def probe(self) -> Availability:
                self.probe_calls += 1
                return Availability(
                    available=available,
                    version="7.6",
                    tool_path="/usr/bin/soffice",
                    reason=reason,
                    checked_at=datetime.now(timezone.utc),
                )

            def convert(self, path: Path) -> _ConvertResult:
                self.convert_calls.append(path)
                return _ConvertResult(content=f"# {path.stem}", metadata={}, success=True, error=None)

        return _Counting()


@pytest.fixture
def counting_backend():
    """Register a probe-counting backend in an emptied registry."""
    from mid.backends.registry import registry

    helper = CountingBatchBackend()
    original = list(registry.list_all())
    registry.clear()

    def register(**kwargs):
        backend = helper.make(**kwargs)
        registry.register(backend)
        return backend

    yield register

    registry.clear()
    for backend in original:
        registry.register(backend)


class TestBatchBackendSingleProbe:
    """`batch --backend` probes once for the whole run, never per file (#70)."""

    def test_probes_once_for_two_files(self, counting_backend, tmp_path: Path) -> None:
        backend = counting_backend(available=True)
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "one.odt").write_text("one", encoding="utf-8")
        (input_dir / "two.odt").write_text("two", encoding="utf-8")
        (input_dir / "notes.txt").write_text("skip", encoding="utf-8")
        output = tmp_path / "out"

        code, out, err = _run(["batch", str(input_dir), "-o", str(output), "--backend", "counting"])

        assert code == 0, f"stderr: {err}"
        assert err == ""
        assert out == "Processed: 2, Succeeded: 2, Failed: 0, Skipped: 1\n"
        assert backend.probe_calls == 1
        assert len(backend.convert_calls) == 2
        assert (output / "one.md").read_text(encoding="utf-8") == "# one"
        assert (output / "two.md").read_text(encoding="utf-8") == "# two"

    def test_unavailable_probes_once_exits_3_and_creates_no_output_dir(self, counting_backend, tmp_path: Path) -> None:
        backend = counting_backend(available=False, reason="soffice missing")
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "one.odt").write_text("one", encoding="utf-8")
        output = tmp_path / "out"

        code, out, err = _run(["batch", str(input_dir), "-o", str(output), "--backend", "counting"])

        assert code == 3
        assert out == ""
        assert err == "error: backend 'counting' unavailable: soffice missing\n"
        assert backend.probe_calls == 1
        assert backend.convert_calls == []
        # #40 regression guard: the pre-flight runs before the output dir exists.
        assert not output.exists()
