"""Shared helper utilities for release bootstrap contract tests."""

from __future__ import annotations

import hashlib
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_tool(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        pytest.skip(f"{name} is required for installer runtime coverage")
    return resolved


def _require_bash_command(bash: str, command: str) -> None:
    probe = subprocess.run([bash, "-lc", f"command -v {command} >/dev/null"], check=False)
    if probe.returncode != 0:
        pytest.skip(f"bash command '{command}' is required for installer runtime coverage")


def _to_bash_path(path: Path) -> str:
    raw = str(path)
    if len(raw) >= 2 and raw[1] == ":":
        suffix = raw[2:].replace("\\", "/")
        return f"/mnt/{raw[0].lower()}{suffix}"
    return raw.replace("\\", "/")


def _run_bash_script(
    bash: str,
    script: Path,
    env: dict[str, str],
    overrides: dict[str, str],
    args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    exports = "; ".join(f"export {key}={shlex.quote(value)}" for key, value in sorted(overrides.items()))
    cmd_parts = [shlex.quote(_to_bash_path(script))]
    if args:
        cmd_parts.extend(shlex.quote(a) for a in args)
    command = f"{exports}; exec bash {' '.join(cmd_parts)}" if exports else f"exec bash {' '.join(cmd_parts)}"
    return subprocess.run(
        [bash, "-lc", command],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
