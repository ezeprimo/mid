"""Detection helpers: which_tool and run_version."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def which_tool(name: str) -> Path | None:
    logger.debug("looking up tool on PATH: %s", name)
    p = shutil.which(name)
    if p:
        logger.info("tool found: %s", name)
        return Path(p)
    logger.info("tool not found on PATH: %s", name)
    return None


def run_version(cmd: list[str], pattern: str | None = None) -> str | None:
    """Run cmd and extract version string. Timeout 2s. May raise TimeoutExpired."""
    logger.debug("running version probe: %s", cmd[0] if cmd else "<empty>")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
    if result.returncode != 0:
        logger.info("version probe failed for %s (exit %d)", cmd[0] if cmd else "?", result.returncode)
        return None
    output = (result.stdout or "") + (result.stderr or "")
    if pattern:
        m = re.search(pattern, output)
        if m:
            version = m.group(1) if m.groups() else m.group(0)
            logger.debug("version probe matched for %s: %s", cmd[0], version)
            return version
        logger.info("version probe found no match for %s", cmd[0])
        return None
    m = re.search(r"\d+\.\d+(?:\.\d+)*(?:\.\d+)?", output)
    if m:
        logger.debug("version probe matched for %s: %s", cmd[0], m.group(0))
        return m.group(0)
    logger.info("version probe found no match for %s", cmd[0])
    return None
