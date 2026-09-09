"""Detection helpers: which_tool and run_version."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def which_tool(name: str) -> Path | None:
    p = shutil.which(name)
    return Path(p) if p else None


def run_version(cmd: list[str], pattern: str | None = None) -> str | None:
    """Run cmd and extract version string. Timeout 2s. May raise TimeoutExpired."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
    if result.returncode != 0:
        return None
    output = (result.stdout or "") + (result.stderr or "")
    if pattern:
        m = re.search(pattern, output)
        if m:
            return m.group(1) if m.groups() else m.group(0)
        return None
    m = re.search(r"\d+\.\d+(?:\.\d+)*(?:\.\d+)?", output)
    return m.group(0) if m else None
