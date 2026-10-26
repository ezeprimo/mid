"""Shared environment resolution for backends (issue #47).

Each backend resolves a tool path and a conversion timeout from its own
environment variables using the same two shapes: an override that must point at
an existing file and falls through when it does not, and a timeout clamped to a
range with a default. Keeping one copy here means a third backend reuses it
instead of copying it again.

What is deliberately *not* here: the probe skeleton. The probes differ in ways
that matter (a platform guard, a 2s clock budget, a COM check versus a CLI
version call), and the never-raise caching lives in ``Backend.is_available``.
Sharing it would need a parameter per difference, which is more coupling than
duplication.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

Viewer = Callable[[str], "Path | None"]


def resolve_env_path(
    env_var: str,
    candidates: Iterable[str],
    finder: Viewer,
    hint: str,
) -> tuple[Path | None, str | None]:
    """Resolve a tool path from an env override, then a candidate chain.

    Args:
        env_var: Environment variable holding an absolute path override.
        candidates: Names tried in order when the override is absent or invalid.
        finder: Resolves one candidate name to a path, or ``None``.
        hint: Message returned when nothing resolves.

    Returns:
        ``(path, None)`` on success or ``(None, hint)`` when unresolved. An
        override that does not point at an existing file is ignored rather than
        raising, so a stale variable keeps the chain working.
    """
    env_path = os.environ.get(env_var)
    if env_path:
        override = Path(env_path)
        if override.is_file():
            return override, None
        logger.info("%s=%s is not an existing file; falling back to the chain", env_var, env_path)

    for name in candidates:
        found = finder(name)
        if found is not None:
            return found, None
    return None, hint


def resolve_timeout(
    env_var: str,
    label: str,
    *,
    default: int = 30,
    minimum: int = 5,
    maximum: int = 300,
) -> int:
    """Resolve a conversion timeout in seconds from the environment.

    Invalid values fall back to ``default`` and out-of-range values are clamped
    to ``[minimum, maximum]`` instead of failing the conversion.
    """
    raw = os.environ.get(env_var)
    if raw is None:
        logger.info("%s timeout: default %ss", label, default)
        return default
    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.info("%s timeout: invalid %s, using %ss", label, env_var, default)
        return default
    if value < minimum:
        logger.info("%s timeout: clamped to minimum %ss", label, minimum)
        return minimum
    if value > maximum:
        logger.info("%s timeout: clamped to maximum %ss", label, maximum)
        return maximum
    logger.info("%s timeout: %ss", label, value)
    return value
