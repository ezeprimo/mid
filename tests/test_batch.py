"""Tests for ``mid batch`` — file discovery, output structure, error handling."""

from __future__ import annotations

import importlib.util
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import pytest

from mid.cli import main


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
# Recursive — preserve
# ===========================================================================


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
