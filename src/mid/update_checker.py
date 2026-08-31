"""Update checker — TTY banner with 24h cache and opt-out.

Implements the first slice banner only, ported from cliol/update_checker.py
adapted to argparse + plain stderr.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path


CACHE_TTL = 86400

# ---------------------------------------------------------------------------
# Cache path
# ---------------------------------------------------------------------------


def get_cache_path() -> Path:
    """Return the cache file path.

    Primary: ``platformdirs.user_cache_dir("mid")/update_cache.json``
    Fallback: ``~/.config/mid/.update_cache.json`` on ImportError or
    missing platformdirs.

    Ensures parent directories exist with 0700 where possible (best-effort).
    """
    try:
        from platformdirs import user_cache_dir  # type: ignore

        base = Path(user_cache_dir("mid"))
        cache_path = base / "update_cache.json"
    except ImportError:
        cache_path = Path.home() / ".config" / "mid" / ".update_cache.json"
    except Exception:
        cache_path = Path.home() / ".config" / "mid" / ".update_cache.json"

    # Best-effort ensure parent exists with 0700; silent on error.
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(cache_path.parent, 0o700)
        except OSError:
            pass
        except NotImplementedError:
            pass
    except OSError:
        pass
    except Exception:
        pass

    return cache_path


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _read_cache() -> dict | None:
    """Read cache file, return None on missing/corrupt/parse failure."""
    try:
        cache_path = get_cache_path()
        if not cache_path.exists():
            return None
        text = cache_path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return None
    except Exception:
        return None


def _write_cache(data: dict) -> None:
    """Atomic write via .tmp + os.replace, dirs 0700 files 0600.

    Silent on OSError.
    """
    try:
        cache_path = get_cache_path()
        # Ensure parent dir
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(cache_path.parent, 0o700)
            except OSError:
                pass
            except NotImplementedError:
                pass
        except OSError:
            pass

        tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        # Alternative tmp naming if suffix handling collides:
        # keep simple .tmp suffix; if cache_path is update_cache.json -> update_cache.json.tmp

        text = json.dumps(data, indent=2)
        tmp_path.write_text(text, encoding="utf-8")
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        except NotImplementedError:
            pass

        os.replace(tmp_path, cache_path)

        try:
            os.chmod(cache_path, 0o600)
        except OSError:
            pass
        except NotImplementedError:
            pass
    except OSError:
        return
    except Exception:
        return


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


def is_newer(latest: str, current: str) -> bool:
    """Return True if *latest* is newer than *current*.

    Strips leading ``v``/``V`` and whitespace. Uses ``packaging.version.Version``
    when available, falls back to simple numeric comparison. Returns False on
    InvalidVersion or parse failure.
    """
    try:

        def _normalize(v: str) -> str:
            v = str(v).strip()
            if v.lower().startswith("v"):
                v = v[1:].strip()
            return v

        latest_n = _normalize(latest)
        current_n = _normalize(current)

        if not latest_n or not current_n:
            return False

        try:
            from packaging.version import InvalidVersion, Version  # type: ignore

            try:
                return Version(latest_n) > Version(current_n)
            except InvalidVersion:
                return False
            except Exception:
                return False
        except ImportError:
            # Fallback simple numeric comparison
            def _parse_simple(v: str) -> list[int] | None:
                parts: list[int] = []
                for segment in v.split("."):
                    if not segment:
                        return None
                    # Extract leading numeric portion (e.g., "1a2" -> 1)
                    num_str = ""
                    for ch in segment:
                        if ch.isdigit():
                            num_str += ch
                        else:
                            break
                    if not num_str:
                        return None
                    # handle large segments that may contain suffix like "1rc1" -> 1
                    try:
                        parts.append(int(num_str))
                    except ValueError:
                        return None
                    # If segment contains non-numeric suffix, we stop parsing further?
                    # For simplicity, if segment has non-digit chars, treat as invalid for simple fallback?
                    # But we already extracted numeric prefix, so allow.
                return parts

            latest_parts = _parse_simple(latest_n)
            current_parts = _parse_simple(current_n)
            if latest_parts is None or current_parts is None:
                return False

            # Pad shorter with zeros for fair comparison
            max_len = max(len(latest_parts), len(current_parts))
            latest_parts += [0] * (max_len - len(latest_parts))
            current_parts += [0] * (max_len - len(current_parts))
            return latest_parts > current_parts
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# Fetch latest version
# ---------------------------------------------------------------------------


def fetch_latest_version(timeout: float = 2.0) -> str | None:
    """Fetch latest release tag from GitHub API.

    Returns normalized version without leading ``v``, or None on any failure.
    Uses lazy ``httpx`` else ``urllib``.
    """
    url = "https://api.github.com/repos/ezeprimo/mid/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mid-update-checker",
    }

    # Try httpx first (lazy import)
    try:
        try:
            import httpx  # type: ignore

            try:
                resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
                if resp.status_code != 200:
                    return None
                try:
                    data = resp.json()
                except Exception:
                    return None
                tag = data.get("tag_name") or data.get("name") or ""
                if not tag:
                    return None
                tag = str(tag).strip()
                if tag.lower().startswith("v"):
                    tag = tag[1:].strip()
                return tag if tag else None
            except Exception:
                return None
        except ImportError:
            # Fallback to urllib
            import urllib.error
            import urllib.request

            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:  # type: ignore[attr-defined]
                    status = getattr(resp, "status", 200)
                    if status != 200:
                        return None
                    body = resp.read().decode("utf-8")
                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError:
                        return None
                    tag = data.get("tag_name") or data.get("name") or ""
                    if not tag:
                        return None
                    tag = str(tag).strip()
                    if tag.lower().startswith("v"):
                        tag = tag[1:].strip()
                    return tag if tag else None
            except Exception:
                return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

_TRUNK_ALLOWLIST: set[tuple[str, ...]] = {
    (),
    ("convert",),
    ("batch",),
    ("help",),
}


def _extract_subcommand(argv: list[str]) -> tuple[str, ...]:
    """Extract subcommand tuple from argv for allowlist check.

    Handles both ``sys.argv`` (with program name) and bare args list.
    Returns empty tuple when no subcommand present.
    """
    if not argv:
        return ()

    # Determine where args start (skip program name if present)
    # Heuristics:
    # - If first element is a known subcommand, treat argv as bare (no program)
    # - If first element starts with '-', it's a flag, not program
    # - Otherwise treat first element as program name and search from index 1
    known = {"convert", "batch", "help"}
    start_idx = 0
    if argv[0] not in known and not argv[0].startswith("-"):
        # Likely program name like "mid" or "mid.exe" or full path
        start_idx = 1
        if start_idx >= len(argv):
            return ()

    # Find first non-flag token as subcommand
    for i in range(start_idx, len(argv)):
        token = argv[i]
        if token.startswith("-"):
            continue
        # Found candidate subcommand
        # Only consider known subcommands as valid; otherwise return tuple with token for allowlist miss
        return (token,)

    return ()


def should_check(argv: list[str] | None = None) -> bool:
    """Return True if update check should run.

    Guards:
    - sys.stderr.isatty() false -> False
    - CI/GITHUB_ACTIONS truthy or TERM == "dumb" -> False
    - --help/-h/--version in argv -> False
    - --json in argv -> False
    - MID_NO_UPDATE_CHECK in 1|true|yes|on -> False
    - trunk allowlist -> False if subcommand not in allowlist
    """
    try:
        # TTY guard
        try:
            if not sys.stderr.isatty():
                return False
        except Exception:
            return False

        # Env guards: CI / GITHUB_ACTIONS / TERM
        def _is_truthy(val: str | None) -> bool:
            if val is None:
                return False
            v = val.strip().lower()
            if not v:
                return False
            if v in {"0", "false", "no", "off"}:
                return False
            return True

        if _is_truthy(os.environ.get("CI")) or _is_truthy(os.environ.get("GITHUB_ACTIONS")):
            return False

        term = os.environ.get("TERM", "")
        if term.strip().lower() == "dumb":
            return False

        # Opt-out env
        mid_no = os.environ.get("MID_NO_UPDATE_CHECK", "")
        if mid_no.strip().lower() in {"1", "true", "yes", "on"}:
            return False

        # Resolve argv
        if argv is None:
            argv = sys.argv

        # Flags that suppress banner
        for arg in argv:
            if arg in ("--help", "-h", "--version"):
                return False

        if "--json" in argv:
            return False

        if "--list-formats" in argv:
            return False

        # Trunk allowlist
        sub = _extract_subcommand(argv)
        if sub not in _TRUNK_ALLOWLIST:
            return False

        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def _format_banner(current: str, latest: str) -> str:
    """Format banner text."""
    if sys.platform == "win32":
        install_line = "  irm https://raw.githubusercontent.com/ezeprimo/mid/main/install.ps1 | iex"
    else:
        install_line = "  curl -fsSL https://raw.githubusercontent.com/ezeprimo/mid/main/install.sh | bash"
    lines = [
        f"Update available: {current} -> {latest}",
        install_line,
        f"  or: pipx install --force 'mid=={latest}'",
        "  https://github.com/ezeprimo/mid/releases",
    ]
    return "\n".join(lines)


def _print_banner(current: str, latest: str) -> None:
    """Print banner to stderr, rich-aware, never raises."""
    try:
        banner = _format_banner(current, latest)
        # Try rich first
        try:
            from rich.console import Console  # type: ignore

            try:
                console = Console(file=sys.stderr, highlight=False)
                console.print(banner)
                return
            except Exception:
                pass
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback plain print
        try:
            print(banner, file=sys.stderr)
        except Exception:
            pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def check_and_notify() -> None:
    """Check for updates and print banner if newer version available.

    - 24h throttle via ``checked_at`` ISO Z
    - Uses cache when within TTL
    - Never raises, never writes to stdout
    """
    try:
        if not should_check():
            return

        # Import current version lazily to avoid circular
        try:
            from mid import __version__ as current_version
        except Exception:
            return

        # Read cache
        cache = _read_cache()

        now = datetime.datetime.now(datetime.timezone.utc)

        # If cache exists and within TTL, use cached value
        if cache is not None:
            checked_at_str = cache.get("checked_at")
            if isinstance(checked_at_str, str):
                try:
                    # Parse ISO Z
                    iso = checked_at_str.replace("Z", "+00:00")
                    checked_at = datetime.datetime.fromisoformat(iso)
                    if checked_at.tzinfo is None:
                        checked_at = checked_at.replace(tzinfo=datetime.timezone.utc)
                    elapsed = (now - checked_at).total_seconds()
                    if elapsed < CACHE_TTL:
                        # Within throttle window: use cached latest_version if newer
                        cached_latest = cache.get("latest_version")
                        if isinstance(cached_latest, str) and cached_latest:
                            if is_newer(cached_latest, current_version):
                                _print_banner(current_version, cached_latest)
                        return
                except Exception:
                    pass  # treat as expired, continue to fetch

        # Fetch latest
        latest = fetch_latest_version()

        # Prepare new cache entry
        new_cache: dict = {}
        # Preserve latest_version if fetch failed but cache had one? Or just store fetched?
        # We store fetched if available, else keep cached latest if present to avoid losing info
        if latest:
            new_cache["latest_version"] = latest
        elif cache and isinstance(cache.get("latest_version"), str):
            new_cache["latest_version"] = cache.get("latest_version")

        new_cache["checked_at"] = now.isoformat().replace("+00:00", "Z")

        # Write cache (even if fetch failed, we throttle)
        try:
            _write_cache(new_cache)
        except Exception:
            pass

        if latest and is_newer(latest, current_version):
            _print_banner(current_version, latest)

    except Exception:
        return
