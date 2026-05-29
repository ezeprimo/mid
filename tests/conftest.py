"""pytest fixtures for mid tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mid.models import ConvertResult


# ---------------------------------------------------------------------------
# Sample directory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_dir(tmp_path: Path) -> Path:
    """Create a flat directory with mixed files for batch tests."""
    d = tmp_path / "input"
    d.mkdir()
    (d / "a.docx").write_text("dummy docx", encoding="utf-8")
    (d / "b.pdf").write_text("dummy pdf", encoding="utf-8")
    (d / "notes.txt").write_text("skip me", encoding="utf-8")
    return d


@pytest.fixture
def nested_dir(tmp_path: Path) -> Path:
    """Create a nested directory tree for recursive batch tests."""
    d = tmp_path / "nested"
    d.mkdir()
    (d / "root.docx").write_text("root", encoding="utf-8")

    sub = d / "sub"
    sub.mkdir()
    (sub / "sub.docx").write_text("sub content", encoding="utf-8")

    sub2 = sub / "sub2"
    sub2.mkdir()
    (sub2 / "deep.pdf").write_text("deep content", encoding="utf-8")
    return d


@pytest.fixture
def collision_dir(tmp_path: Path) -> Path:
    """Create files with identical stems in different subdirs."""
    d = tmp_path / "collision"
    d.mkdir()
    (d / "report.docx").write_text("root report", encoding="utf-8")

    a = d / "a"
    a.mkdir()
    (a / "report.docx").write_text("a report", encoding="utf-8")

    b = d / "b"
    b.mkdir()
    (b / "report.xlsx").write_text("b report", encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# Mock helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_convert_success():
    """Make ``mid.cli.convert_file`` always succeed.

    Use this in batch tests to avoid needing real MarkItDown.
    """
    with patch("mid.cli.convert_file") as mock:
        mock.return_value = ConvertResult(
            content="# Converted by mock",
            metadata={"source": "test", "format": "docx", "success": True},
            success=True,
            error=None,
        )
        yield mock


@pytest.fixture
def mock_convert_failure():
    """Make ``mid.cli.convert_file`` always fail."""
    with patch("mid.cli.convert_file") as mock:
        mock.return_value = ConvertResult(
            content="",
            metadata={},
            success=False,
            error="mock simulated failure",
        )
        yield mock
