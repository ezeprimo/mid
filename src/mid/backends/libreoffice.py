"""LibreOffice backend — headless conversion via soffice."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from mid.backends.base import Availability, Backend
from mid.backends.detection import run_version, which_tool
from mid.models import ConvertResult


def _resolve_tool_path() -> tuple[Path | None, str | None]:
    """Resolve LibreOffice tool path.

    Precedence: MID_LIBREOFFICE_PATH (must be existing file) else chain
    soffice -> libreoffice -> soffice.bin via which_tool.

    Returns (Path|None, str|None) where second is error hint if needed.
    """
    env_path = os.environ.get("MID_LIBREOFFICE_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p, None
        # invalid env falls through to chain (LIBRE-08)
    for name in ("soffice", "libreoffice", "soffice.bin"):
        found = which_tool(name)
        if found is not None:
            return found, None
    return None, "LibreOffice not found — install LibreOffice 7.6+ (libreoffice-writer)"


def _resolve_timeout() -> int:
    """Resolve convert timeout from MID_LIBREOFFICE_TIMEOUT, clamp 5..300 default 30."""
    raw = os.environ.get("MID_LIBREOFFICE_TIMEOUT")
    if raw is None:
        return 30
    try:
        val = int(raw)
    except (ValueError, TypeError):
        return 30
    if val < 5:
        return 5
    if val > 300:
        return 300
    return val


def _locate_output(tmp: Path, stem: str) -> Path | None:
    """Locate converted HTML output: stem.html else largest *.html size>0."""
    candidate = tmp / f"{stem}.html"
    if candidate.is_file():
        try:
            if candidate.stat().st_size > 0:
                return candidate
        except OSError:
            pass
    # glob fallback: largest size>0
    pattern = str(tmp / "*.html")
    files = glob.glob(pattern)
    best: Path | None = None
    best_size = -1
    for f in files:
        p = Path(f)
        try:
            sz = p.stat().st_size
        except OSError:
            continue
        if sz > 0 and sz > best_size:
            best_size = sz
            best = p
    return best


class LibreOfficeBackend(Backend):
    """Headless LibreOffice backend."""

    name: str = "libreoffice"
    display_name: str = "LibreOffice"
    opt_in: bool = False
    supported_extensions: ClassVar[frozenset[str]] = frozenset(
        {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"}
    )
    required_tools: ClassVar[tuple[str, ...]] = ("soffice", "libreoffice", "soffice.bin")

    def probe(self) -> Availability:
        """Probe availability — never raise, cache only True via base."""
        try:
            tool_path, hint = _resolve_tool_path()
            if tool_path is None:
                return Availability(
                    available=False,
                    version=None,
                    tool_path=None,
                    reason=hint or "LibreOffice not found — install LibreOffice 7.6+ (libreoffice-writer)",
                    checked_at=datetime.now(timezone.utc),
                )
            # run_version with 2s timeout and regex
            try:
                version = run_version([str(tool_path), "--version"], r"(\d+\.\d+(?:\.\d+)*)")
            except subprocess.TimeoutExpired:
                return Availability(
                    available=False,
                    version=None,
                    tool_path=str(tool_path),
                    reason="probe timed out",
                    checked_at=datetime.now(timezone.utc),
                )
            if version is None:
                return Availability(
                    available=False,
                    version=None,
                    tool_path=str(tool_path),
                    reason="could not determine version",
                    checked_at=datetime.now(timezone.utc),
                )
            return Availability(
                available=True,
                version=version,
                tool_path=str(tool_path),
                reason=None,
                checked_at=datetime.now(timezone.utc),
            )
        except Exception as exc:  # never-raise
            return Availability(
                available=False,
                version=None,
                tool_path=None,
                reason=str(exc) or "probe failed",
                checked_at=datetime.now(timezone.utc),
            )

    def convert(self, path: Path) -> ConvertResult:
        """Convert via headless soffice -> HTML -> MarkItDown."""
        try:
            # validate path
            if not path.is_file():
                return ConvertResult(content="", metadata={}, success=False, error=f"file not found: {path}")
            ext = path.suffix.lower()
            if ext not in self.supported_extensions:
                return ConvertResult(content="", metadata={}, success=False, error=f"unsupported format {ext}")
            # resolve tool and timeout
            tool_path, hint = _resolve_tool_path()
            if tool_path is None:
                return ConvertResult(content="", metadata={}, success=False, error=hint or "LibreOffice not found")
            timeout = _resolve_timeout()

            with tempfile.TemporaryDirectory(prefix="mid-libreoffice-") as tmpdir:
                tmp = Path(tmpdir)
                # copy input into tmp
                tmp_input = tmp / path.name
                try:
                    shutil.copy2(path, tmp_input)
                except OSError as exc:
                    return ConvertResult(content="", metadata={}, success=False, error=str(exc))

                # run headless soffice
                cmd = [
                    str(tool_path),
                    "--headless",
                    "--invisible",
                    "--norestore",
                    "--nolockcheck",
                    "--convert-to",
                    "html:XHTML Writer File:UTF8",
                    "--outdir",
                    str(tmp),
                    str(tmp_input),
                ]
                try:
                    result = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=timeout)
                except subprocess.TimeoutExpired:
                    return ConvertResult(
                        content="",
                        metadata={},
                        success=False,
                        error=f"conversion timed out after {timeout}s (profile lock?)",
                    )
                except Exception as exc:
                    return ConvertResult(content="", metadata={}, success=False, error=str(exc))

                if result.returncode != 0:
                    stderr = (result.stderr or result.stdout or "").strip()
                    truncated = stderr[:500]
                    # profile lock hint
                    if "lock" in truncated.lower():
                        truncated += " (profile lock — try closing LibreOffice)"
                    return ConvertResult(content="", metadata={}, success=False, error=truncated or "conversion failed")

                # locate output
                out = _locate_output(tmp, path.stem)
                if out is None:
                    return ConvertResult(content="", metadata={}, success=False, error="conversion produced no output")
                # 20MB cap
                try:
                    size = out.stat().st_size
                except OSError as exc:
                    return ConvertResult(content="", metadata={}, success=False, error=str(exc))
                if size > 20 * 1024 * 1024:
                    return ConvertResult(content="", metadata={}, success=False, error="output exceeds 20 MB limit")
                if size == 0:
                    return ConvertResult(content="", metadata={}, success=False, error="conversion produced empty output")

                # read utf-8 strict
                try:
                    html_text = out.read_text(encoding="utf-8")
                    # strict check: encode/decode ensures strict? read_text with strict will raise UnicodeDecodeError
                    # but Python's read_text with encoding utf-8 uses strict by default
                    # To be explicit, we already rely on that; if decode error, except below
                    _ = html_text.encode("utf-8")  # ensure encodable
                except UnicodeDecodeError as exc:
                    return ConvertResult(content="", metadata={}, success=False, error=str(exc))
                except Exception as exc:
                    return ConvertResult(content="", metadata={}, success=False, error=str(exc))

                # delegate to MarkitDownConverter
                try:
                    from mid.converters.markitdown import MarkitDownConverter
                except Exception as exc:
                    return ConvertResult(content="", metadata={}, success=False, error=str(exc))

                try:
                    md = MarkitDownConverter()
                    md_result = md.convert(out)
                    if not md_result.success:
                        return ConvertResult(
                            content="", metadata={}, success=False, error=md_result.error or "delegation failed"
                        )
                    return ConvertResult(
                        content=md_result.content,
                        metadata={"source": path.name, "format": ext.lstrip("."), "success": True},
                        success=True,
                        error=None,
                    )
                except Exception as exc:
                    return ConvertResult(content="", metadata={}, success=False, error=str(exc))
        except Exception as exc:  # never-raise outer
            return ConvertResult(content="", metadata={}, success=False, error=str(exc) or "conversion failed")
