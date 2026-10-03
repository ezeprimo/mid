"""Structured logging setup for the ``mid`` CLI.

Levels (``-v``/``--verbose`` is countable):

* 0 (default) → ``WARNING``
* 1 (``-v``)  → ``INFO``
* 2+ (``-vv``) → ``DEBUG``

When the CLI flags are absent, the ``MID_VERBOSE`` (``0``/``1``/``2``) and
``MID_LOG_FILE`` environment variables apply. An explicit CLI value always
wins over the environment.

Console records go to **stderr only** so ``stdout`` stays pure Markdown
(or pure JSON with ``--json``). The format carries timestamp + level +
module: ``"%(asctime)s %(levelname)s %(name)s: %(message)s"``.

Colors are never emitted, so ``NO_COLOR`` is respected trivially.

``setup_logging`` is idempotent: repeated calls remove previously installed
``mid`` handlers before adding fresh ones, so no duplicate records appear.
"""

from __future__ import annotations

import logging
import os
import sys

#: Log record format: timestamp + level + module, per issue 44.
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

#: Marker attribute tagging handlers owned by this module (for idempotency).
_MARKER = "_mid_logging_handler"

#: Verbosity env vars honored when the matching CLI flag is absent.
VERBOSE_ENV_VAR = "MID_VERBOSE"
LOG_FILE_ENV_VAR = "MID_LOG_FILE"


def _parse_verbose_raw(raw: str | None) -> int | None:
    """Parse a raw verbosity value; ``None`` when missing/invalid."""
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except (ValueError, TypeError, AttributeError):
        return None
    if value < 0:
        return None
    return value


def resolve_verbose(cli_value: int | None) -> int:
    """Resolve the effective verbosity count.

    Precedence: explicit CLI value, else ``MID_VERBOSE`` env, else ``0``.
    """
    if cli_value is not None:
        return max(0, int(cli_value))
    env_value = _parse_verbose_raw(os.environ.get(VERBOSE_ENV_VAR))
    if env_value is not None:
        return env_value
    return 0


def resolve_log_file(cli_value: str | None) -> str | None:
    """Resolve the effective log-file path: CLI value else ``MID_LOG_FILE``."""
    if cli_value:
        return cli_value
    env_value = os.environ.get(LOG_FILE_ENV_VAR)
    if env_value and env_value.strip():
        return env_value.strip()
    return None


def _level_for(verbose_count: int) -> int:
    if verbose_count >= 2:
        return logging.DEBUG
    if verbose_count == 1:
        return logging.INFO
    return logging.WARNING


def setup_logging(
    verbose_count: int | None = None,
    log_file: str | None = None,
) -> None:
    """Configure the root logger for ``mid``. Idempotent, never raises.

    Args:
        verbose_count: Explicit ``-v`` count (``None`` → ``MID_VERBOSE``/``0``).
        log_file: Explicit ``--log-file`` path (``None`` → ``MID_LOG_FILE``).
    """
    try:
        count = resolve_verbose(verbose_count)
        target = resolve_log_file(log_file)
        level = _level_for(count)

        root = logging.getLogger()
        # Idempotency: drop handlers previously installed by this module.
        for handler in list(root.handlers):
            if getattr(handler, _MARKER, False):
                root.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass

        formatter = logging.Formatter(LOG_FORMAT)

        # Console handler → stderr only, never stdout. No colors by default,
        # so NO_COLOR needs no special handling.
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        setattr(console, _MARKER, True)
        root.addHandler(console)

        if target:
            try:
                file_handler = logging.FileHandler(target, encoding="utf-8")
            except OSError:
                file_handler = None
            if file_handler is not None:
                file_handler.setFormatter(formatter)
                setattr(file_handler, _MARKER, True)
                root.addHandler(file_handler)

        root.setLevel(level)
    except Exception:
        # Logging setup must never break the CLI.
        pass
