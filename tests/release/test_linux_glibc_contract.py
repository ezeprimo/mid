"""Contract tests for the Linux release binary glibc floor (issue #57)."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from helpers import _to_bash_path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANYLINUX_SCRIPT = REPO_ROOT / "scripts" / "build-linux-manylinux.sh"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build.sh"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
README = REPO_ROOT / "README.md"

GLIBC_FLOOR = "2.28"
MANYLINUX_IMAGE = "quay.io/pypa/manylinux_2_28_x86_64"
# Oldest image the smoke runs on; must be older than both the build image and
# ubuntu-latest, otherwise it cannot catch a too-new glibc requirement.
SMOKE_IMAGE = "ubuntu:20.04"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env is not None:
        merged.update(env)
    return subprocess.run(
        ["bash", _to_bash_path(MANYLINUX_SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=merged,
    )


def _run_build_script(*args: str, assignments: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    # Environment variables do not cross the Windows-to-WSL bridge unless they
    # are prefixed explicitly, so assignments are inlined into the command.
    prefix = ""
    if assignments:
        prefix = "; ".join(f"export {key}={shlex.quote(value)}" for key, value in sorted(assignments.items()))
    command = f"{prefix + '; ' if prefix else ''}exec bash {shlex.quote(_to_bash_path(BUILD_SCRIPT))} " + " ".join(
        shlex.quote(a) for a in args
    )
    return subprocess.run(
        ["bash", "-lc", command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_manylinux_build_script_declares_glibc_floor_image() -> None:
    assert MANYLINUX_SCRIPT.is_file(), "scripts/build-linux-manylinux.sh must exist"

    content = _read(MANYLINUX_SCRIPT)

    assert MANYLINUX_IMAGE in content
    assert GLIBC_FLOOR in content
    assert "scripts/build.sh" in content


def test_print_command_exposes_container_invocation_for_manylinux_build() -> None:
    result = _run_script(
        "--print-command",
        "--clean",
        "--version",
        "v1.2.3",
        "--output-dir",
        "dist",
    )

    assert result.returncode == 0
    assert result.stderr == ""
    printed = result.stdout
    assert "docker run" in printed
    assert MANYLINUX_IMAGE in printed
    assert f"{_to_bash_path(REPO_ROOT)}:/work" in printed
    assert "scripts/build.sh" in printed
    assert "--version v1.2.3" in printed
    assert "--output-dir /work/dist" in printed
    assert "--clean" in printed


def test_output_dir_outside_repository_exits_2() -> None:
    result = _run_script("--print-command", "--output-dir", "/tmp/outside-repo")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "--output-dir must stay inside the repository" in result.stderr


def test_absolute_output_dir_inside_repository_maps_to_container_path() -> None:
    result = _run_script("--print-command", "--output-dir", f"{_to_bash_path(REPO_ROOT)}/dist")

    assert result.returncode == 0
    assert "--output-dir /work/dist" in result.stdout


def test_print_command_honours_image_override() -> None:
    result = _run_script("--print-command", "--image", "quay.io/pypa/manylinux_2_34_x86_64")

    assert result.returncode == 0
    assert "quay.io/pypa/manylinux_2_34_x86_64" in result.stdout
    assert MANYLINUX_IMAGE not in result.stdout


def test_unknown_option_exits_2_with_error_and_no_stdout() -> None:
    result = _run_script("--nope")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "unknown option: --nope" in result.stderr


def test_version_without_value_exits_2_with_error() -> None:
    result = _run_script("--version")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "--version requires a value" in result.stderr


def test_release_workflow_builds_linux_binary_through_manylinux_script() -> None:
    content = _read(RELEASE_WORKFLOW)

    assert "scripts/build-linux-manylinux.sh" in content


def test_release_workflow_runs_build_and_smoke_on_different_images() -> None:
    workflow = _read(RELEASE_WORKFLOW)
    script = _read(MANYLINUX_SCRIPT)

    # The glibc floor is owned by the build script, so the workflow must not
    # duplicate (and silently drift from) that image name.
    assert MANYLINUX_IMAGE not in workflow
    assert f"manylinux_2_{GLIBC_FLOOR.split('.')[1]}" in script
    assert SMOKE_IMAGE in workflow
    # The smoke image must be a different, older Ubuntu release than
    # ubuntu-latest (24.04) so a too-new glibc requirement fails the job.
    smoke_major = int(re.search(r"ubuntu:(\d+)\.", SMOKE_IMAGE).group(1))
    assert smoke_major < 24
    assert SMOKE_IMAGE not in script


def test_release_workflow_smoke_uses_the_older_image_for_linux_binary() -> None:
    content = _read(RELEASE_WORKFLOW)

    linux_smoke_steps = [
        block for block in content.split("- name:") if "Linux" in block.splitlines()[0] and "docker run" in block
    ]

    assert linux_smoke_steps, "Linux smoke steps must run the binary inside a container"
    for block in linux_smoke_steps:
        assert SMOKE_IMAGE in block, f"Linux smoke step is missing {SMOKE_IMAGE}"


def test_ci_workflow_builds_the_linux_binary_before_release() -> None:
    # release.yml only runs on tags, so the build path needs a pull-request
    # guard; otherwise a broken build script ships unnoticed.
    content = _read(CI_WORKFLOW)

    assert "scripts/build-linux-manylinux.sh" in content
    assert SMOKE_IMAGE in content


def test_readme_documents_linux_binary_glibc_floor() -> None:
    content = _read(README)

    assert "glibc" in content.lower()
    assert GLIBC_FLOOR in content


def test_build_script_rejects_missing_mid_build_python_override() -> None:
    result = _run_build_script(
        "--version",
        "9.9.9",
        assignments={"MID_BUILD_PYTHON": "/nonexistent/python"},
    )

    assert result.returncode == 2
    assert "MID_BUILD_PYTHON" in result.stderr


def test_build_script_preserves_version_mismatch_error_with_override() -> None:
    result = _run_build_script(
        "--version",
        "9.9.9",
        assignments={"MID_BUILD_PYTHON": _to_bash_path(Path(sys.executable))},
    )

    assert result.returncode == 1
    assert "version mismatch" in result.stderr
