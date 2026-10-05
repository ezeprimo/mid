"""`mid doctor` diagnostics — environment probes that never raise.

Every probe is wrapped so failures become findings (``ok=False``) instead of
tracebacks. Human output goes to stdout; logs stay on stderr (configured in
``cli.main`` before dispatch).
"""

from __future__ import annotations

import json
import sys


def _check_python() -> dict:
    """Probe the interpreter version and executable path."""
    try:
        version = sys.version
        executable = sys.executable
        ok = sys.version_info >= (3, 10)
        if ok:
            status = "ok"
            detail = f"{version} | executable: {executable}"
        else:
            status = "fail"
            detail = f"Python 3.10+ required, found {version} | executable: {executable}"
        return {"name": "python", "ok": ok, "status": status, "detail": detail}
    except Exception as exc:  # never-raise
        return {"name": "python", "ok": False, "status": "fail", "detail": f"probe failed: {exc}"}


def _check_mid() -> dict:
    """Probe the mid package version."""
    try:
        from mid import __version__ as ver

        return {"name": "mid", "ok": True, "status": "ok", "detail": f"mid {ver}"}
    except Exception as exc:  # never-raise
        return {"name": "mid", "ok": False, "status": "fail", "detail": f"probe failed: {exc}"}


def _check_markitdown() -> dict:
    """Probe the markitdown dependency."""
    try:
        import importlib

        try:
            importlib.import_module("markitdown")
        except Exception:
            return {
                "name": "markitdown",
                "ok": False,
                "status": "fail",
                "detail": "markitdown not installed; install with: pip install 'markitdown[all]'",
            }
        try:
            from importlib import metadata as importlib_metadata

            version = importlib_metadata.version("markitdown")
        except Exception:
            version = None
        if version:
            detail = f"markitdown {version}"
        else:
            detail = "markitdown installed (version unknown)"
        return {"name": "markitdown", "ok": True, "status": "ok", "detail": detail}
    except Exception as exc:  # never-raise
        return {"name": "markitdown", "ok": False, "status": "fail", "detail": f"probe failed: {exc}"}


def _check_ffmpeg() -> dict:
    """Probe ffmpeg availability (optional dependency)."""
    try:
        from mid.backends import detection as det

        try:
            path = det.which_tool("ffmpeg")
        except Exception as exc:  # never-raise -> finding
            return {
                "name": "ffmpeg",
                "ok": False,
                "status": "fail",
                "detail": f"ffmpeg probe failed: {exc} (optional)",
            }
        if path is None:
            return {
                "name": "ffmpeg",
                "ok": False,
                "status": "fail",
                "detail": "ffmpeg not found on PATH (optional; install ffmpeg for media support)",
            }
        try:
            version = det.run_version(["ffmpeg", "-version"])
        except Exception as exc:  # TimeoutExpired and friends -> finding
            return {
                "name": "ffmpeg",
                "ok": False,
                "status": "fail",
                "detail": f"ffmpeg version probe failed: {exc} (optional)",
            }
        if version:
            detail = f"ffmpeg {version} at {path} (optional)"
        else:
            detail = f"ffmpeg found at {path} (version unknown, optional)"
        return {"name": "ffmpeg", "ok": True, "status": "ok", "detail": detail}
    except Exception as exc:  # never-raise
        return {"name": "ffmpeg", "ok": False, "status": "fail", "detail": f"ffmpeg probe failed: {exc} (optional)"}


def _check_backends() -> list[dict]:
    """Probe every registered backend. Never raises."""
    try:
        try:
            from mid.backends import registry
        except Exception as exc:
            return [
                {
                    "name": "backends",
                    "ok": False,
                    "status": "fail",
                    "detail": f"backend registry unavailable: {exc}",
                    "available": False,
                    "version": None,
                    "tool_path": None,
                    "reason": str(exc),
                }
            ]
        try:
            backends = list(registry.list_all())
        except Exception as exc:
            return [
                {
                    "name": "backends",
                    "ok": False,
                    "status": "fail",
                    "detail": f"backend listing failed: {exc}",
                    "available": False,
                    "version": None,
                    "tool_path": None,
                    "reason": str(exc),
                }
            ]
        checks: list[dict] = []
        for b in backends:
            try:
                name = getattr(b, "name", "?")
            except Exception:
                name = "?"
            try:
                try:
                    # Doctor is explicit consent to probe, including opt-in
                    # backends (same doctrine as `convert --backend X`).
                    avail = b.is_available(refresh=True)
                except Exception as exc:
                    checks.append(
                        {
                            "name": f"backend:{name}",
                            "ok": False,
                            "status": "fail",
                            "detail": f"probe raised {exc}",
                            "available": False,
                            "version": None,
                            "tool_path": None,
                            "reason": str(exc),
                        }
                    )
                    continue
                available = bool(getattr(avail, "available", False))
                version = getattr(avail, "version", None)
                tool_path = getattr(avail, "tool_path", None)
                reason = getattr(avail, "reason", None)
                if available:
                    parts = []
                    if version:
                        parts.append(str(version))
                    if tool_path:
                        parts.append(f"at {tool_path}")
                    detail = "available" + (f" ({', '.join(parts)})" if parts else "")
                    checks.append(
                        {
                            "name": f"backend:{name}",
                            "ok": True,
                            "status": "ok",
                            "detail": detail,
                            "available": True,
                            "version": version,
                            "tool_path": str(tool_path) if tool_path is not None else None,
                            "reason": reason,
                        }
                    )
                else:
                    detail = reason or "unavailable"
                    # LibreOffice on Linux is optional — label it as such with hint.
                    if name == "libreoffice":
                        if "optional" not in detail.lower():
                            if "install" in detail.lower():
                                detail = f"{detail} (optional)"
                            else:
                                detail = f"{detail} (optional; install LibreOffice 7.6+ (libreoffice-writer))"
                    checks.append(
                        {
                            "name": f"backend:{name}",
                            "ok": False,
                            "status": "fail",
                            "detail": detail,
                            "available": False,
                            "version": version,
                            "tool_path": str(tool_path) if tool_path is not None else None,
                            "reason": reason,
                        }
                    )
            except Exception as exc:  # never-raise per backend
                try:
                    label = f"backend:{getattr(b, 'name', '?')}"
                except Exception:
                    label = "backend:?"
                checks.append(
                    {
                        "name": label,
                        "ok": False,
                        "status": "fail",
                        "detail": f"probe failed: {exc}",
                        "available": False,
                        "version": None,
                        "tool_path": None,
                        "reason": str(exc),
                    }
                )
        # Informational office check on non-Windows (not registered there).
        try:
            has_office = registry.get("office") is not None
        except Exception:
            has_office = False
        if not has_office:
            checks.append(
                {
                    "name": "backend:office",
                    "ok": True,
                    "status": "n/a",
                    "detail": "requires Windows (win32)",
                    "available": False,
                    "version": None,
                    "tool_path": None,
                    "reason": "requires Windows (win32)",
                }
            )
        return checks
    except Exception as exc:  # never-raise
        return [
            {
                "name": "backends",
                "ok": False,
                "status": "fail",
                "detail": f"probe failed: {exc}",
                "available": False,
                "version": None,
                "tool_path": None,
                "reason": str(exc),
            }
        ]


def _check_cache() -> dict:
    """Probe cache-dir and tmp writability."""
    try:
        try:
            from mid.update_checker import get_cache_path
        except Exception as exc:
            return {
                "name": "cache/tmp",
                "ok": False,
                "status": "fail",
                "detail": f"cache probe failed: {exc}",
            }
        try:
            cache_path = get_cache_path()
            cache_str = str(cache_path)
        except Exception as exc:
            return {
                "name": "cache/tmp",
                "ok": False,
                "status": "fail",
                "detail": f"cache path unwritable: {exc}",
            }
        try:
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", delete=True) as tf:
                tf.write("ok")
                tf.flush()
        except Exception as exc:
            return {
                "name": "cache/tmp",
                "ok": False,
                "status": "fail",
                "detail": f"tmp unwritable: {exc}; cache: {cache_str}",
            }
        return {
            "name": "cache/tmp",
            "ok": True,
            "status": "ok",
            "detail": f"cache: {cache_str} writable; tmp writable",
        }
    except Exception as exc:  # never-raise
        return {"name": "cache/tmp", "ok": False, "status": "fail", "detail": f"probe failed: {exc}"}


def _check_update() -> dict:
    """Direct connectivity probe of the update checker (ignores TTY guards)."""
    try:
        try:
            from mid.update_checker import fetch_latest_version
        except Exception as exc:
            return {
                "name": "update-checker",
                "ok": False,
                "status": "fail",
                "detail": f"offline or unreachable (non-blocking): {exc}",
            }
        try:
            latest = fetch_latest_version(timeout=2.0)
        except Exception as exc:
            return {
                "name": "update-checker",
                "ok": False,
                "status": "fail",
                "detail": f"offline or unreachable (non-blocking): {exc}",
            }
        if latest:
            return {
                "name": "update-checker",
                "ok": True,
                "status": "ok",
                "detail": f"reachable, latest: {latest} (non-blocking)",
            }
        return {
            "name": "update-checker",
            "ok": False,
            "status": "fail",
            "detail": "offline or unreachable (non-blocking)",
        }
    except Exception as exc:  # never-raise
        return {
            "name": "update-checker",
            "ok": False,
            "status": "fail",
            "detail": f"offline or unreachable (non-blocking): {exc}",
        }


def run_checks() -> list[dict]:
    """Run every probe and return the finding list. Never raises."""
    checks: list[dict] = []
    for fn in (_check_python, _check_mid, _check_markitdown, _check_ffmpeg):
        try:
            checks.append(fn())
        except Exception as exc:  # belt-and-suspenders
            checks.append(
                {
                    "name": getattr(fn, "__name__", "check"),
                    "ok": False,
                    "status": "fail",
                    "detail": f"probe failed: {exc}",
                }
            )
    try:
        checks.extend(_check_backends())
    except Exception as exc:  # never-raise
        checks.append(
            {"name": "backends", "ok": False, "status": "fail", "detail": f"probe failed: {exc}"}
        )
    for fn in (_check_cache, _check_update):
        try:
            checks.append(fn())
        except Exception as exc:  # belt-and-suspenders
            checks.append(
                {
                    "name": getattr(fn, "__name__", "check"),
                    "ok": False,
                    "status": "fail",
                    "detail": f"probe failed: {exc}",
                }
            )
    return checks


def overall_ok(checks: list[dict]) -> bool:
    """Return True when every check has ``ok`` True."""
    try:
        return all(bool(c.get("ok")) for c in checks)
    except Exception:
        return False


def render_human(checks: list[dict]) -> str:
    """Render one line per check plus a final summary line."""
    try:
        lines: list[str] = []
        for c in checks:
            try:
                name = c.get("name", "?")
                ok = bool(c.get("ok"))
                status = c.get("status", "ok" if ok else "fail")
                detail = str(c.get("detail", ""))
                # Keep exactly one line per check.
                detail = " ".join(detail.split())
                marker = "ok" if ok else "FAIL"
                lines.append(f"{name}: {marker} [{status}] {detail}")
            except Exception:
                lines.append("check: FAIL [fail] render failed")
        findings = sum(1 for c in checks if not c.get("ok"))
        if findings == 0:
            lines.append("doctor: all checks passed")
        else:
            lines.append(f"doctor: {findings} finding(s)")
        return "\n".join(lines)
    except Exception as exc:  # never-raise
        return f"doctor: 1 finding(s)\nrender failed: {exc}"


def _mid_version_safe() -> str:
    try:
        from mid import __version__ as ver

        return str(ver)
    except Exception:
        return "unknown"


def _python_version_safe() -> str:
    try:
        return str(sys.version)
    except Exception:
        return "unknown"


def render_json_payload(checks: list[dict]) -> dict:
    """Render the ``--json`` payload dict."""
    try:
        return {
            "ok": overall_ok(checks),
            "mid_version": _mid_version_safe(),
            "python": _python_version_safe(),
            "checks": checks,
        }
    except Exception as exc:  # never-raise
        return {
            "ok": False,
            "mid_version": _mid_version_safe(),
            "python": _python_version_safe(),
            "checks": checks,
            "error": str(exc),
        }


def handler_doctor(args) -> None:
    """Handle ``mid doctor`` — print to stdout, exit 0/1. Never tracebacks."""
    try:
        checks = run_checks()
        use_json = bool(getattr(args, "json", False))
        if use_json:
            payload = render_json_payload(checks)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_human(checks))
        sys.exit(0 if overall_ok(checks) else 1)
    except SystemExit:
        raise
    except Exception as exc:  # unexpected -> printed finding + exit 1
        try:
            print(f"doctor: 1 finding(s)\nunexpected error: {exc}")
        except Exception:
            pass
        sys.exit(1)
