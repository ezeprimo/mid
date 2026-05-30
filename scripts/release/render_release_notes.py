"""Render release notes for mid distribution releases."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


def _render_operator_sections(tag: str, package_version: str, repo: str) -> list[tuple[str, list[str]]]:
    install_ps1 = f"https://raw.githubusercontent.com/{repo}/{tag}/install.ps1"
    install_sh = f"https://raw.githubusercontent.com/{repo}/{tag}/install.sh"

    return [
        ("Install Windows", [f"`irm {install_ps1} | iex`"]),
        ("Install Linux", [f"`curl -fsSL {install_sh} | bash`"]),
        (
            "Version Pinning",
            [
                f"`$env:MID_VERSION={tag}; irm {install_ps1} | iex`",
                f"`MID_VERSION={tag} curl -fsSL {install_sh} | bash`",
            ],
        ),
        (
            "Fallback (pipx/pip)",
            [
                f"`pipx install mid=={package_version}`",
                f"`python -m pip install --user mid=={package_version}`",
            ],
        ),
        (
            "Rollback",
            [
                "Re-run install with an older pinned version:",
                "`MID_VERSION=vX.Y.Z ...`",
            ],
        ),
        (
            "Uninstall",
            [
                "Phase 1 uninstall is manual removal of the installed binary",
                "and cleanup of the managed PATH entry if present.",
            ],
        ),
    ]


def normalize_version(tag_or_version: str) -> tuple[str, str]:
    """Return (tag, pep440_version)."""
    value = tag_or_version.strip()
    if not value:
        raise ValueError("version cannot be empty")
    if value.startswith("v"):
        return value, value[1:]
    return f"v{value}", value


def render_release_notes(tag: str, package_version: str, repo: str) -> str:
    """Return markdown notes containing required operator sections."""
    lines: list[str] = [f"# mid {tag}", ""]
    for heading, content_lines in _render_operator_sections(tag, package_version, repo):
        lines.append(f"## {heading}")
        lines.extend(content_lines)
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render release notes markdown")
    parser.add_argument("--version", required=True, help="Tag or package version (vX.Y.Z or X.Y.Z)")
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/name format")
    parser.add_argument("--output", required=True, help="Output markdown path")
    args = parser.parse_args(argv)

    tag, package_version = normalize_version(args.version)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_release_notes(tag, package_version, args.repo), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
