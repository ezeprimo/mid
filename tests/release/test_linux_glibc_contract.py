"""Contract tests for the Linux release binary glibc floor (issue #57)."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from helpers import _to_bash_path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANYLINUX_SCRIPT = REPO_ROOT / "scripts" / "build-linux-manylinux.sh"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build.sh"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
INSTALL_SMOKE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "install-smoke.yml"
README = REPO_ROOT / "README.md"

GLIBC_FLOOR = "2.28"
MANYLINUX_IMAGE_TAG = "quay.io/pypa/manylinux_2_28_x86_64"
# Images the smoke runs on. They must be different from the build container and
# older than ubuntu-latest, otherwise a too-new glibc requirement cannot be
# caught.
SMOKE_IMAGE = "ubuntu:20.04"
# Cheapest widely-maintained distribution whose glibc equals the documented
# floor; a functional run there is the only real proof of the claim.
FLOOR_IMAGE = "rockylinux:8"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", _to_bash_path(MANYLINUX_SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
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


def _print_command(*args: str) -> subprocess.CompletedProcess[str]:
    return _run_script("--print-command", *args)


def test_manylinux_build_script_pins_the_image_by_digest() -> None:
    content = _read(MANYLINUX_SCRIPT)

    # A mutable tag would let an upstream retag change the toolchain, and with
    # it the dependency resolution, of an artifact that promises a glibc floor.
    assert re.search(re.escape(MANYLINUX_IMAGE_TAG) + r"@sha256:[0-9a-f]{64}", content), (
        "the build image must be pinned by digest"
    )
    assert "scripts/build.sh" in content


def test_print_command_exposes_container_invocation_for_manylinux_build() -> None:
    result = _print_command("--clean", "--version", "v1.2.3", "--output-dir", "dist")

    assert result.returncode == 0
    assert result.stderr == ""
    printed = result.stdout
    assert "docker run" in printed
    assert MANYLINUX_IMAGE_TAG in printed
    assert f"{_to_bash_path(REPO_ROOT)}:/work" in printed
    assert "scripts/build.sh" in printed
    assert "--version v1.2.3" in printed
    assert "--output-dir /work/dist" in printed
    assert "--clean" in printed


def _printed_argv(*args: str) -> list[str]:
    printed = _print_command(*args)
    assert printed.returncode == 0, printed.stderr
    # The printed form is bash's own %q output, which may use ANSI-C quoting
    # ($'...') for the multi-line inner script. Let bash expand it and stub
    # `docker` so the real argv can be inspected without running anything.
    # The probe goes through a file: an inline `bash -c` string does not
    # survive the Windows-to-WSL bridge used to run these tests locally.
    probe = "docker() { printf '%s\\0' \"$@\"; }\n" + printed.stdout
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "print-command-probe.sh"
        # newline="" keeps the LF bytes bash needs; Windows text mode would
        # rewrite them as CRLF and break the ANSI-C quoted inner script.
        script.write_text(probe, encoding="utf-8", newline="\n")
        expanded = subprocess.run(
            ["bash", _to_bash_path(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    assert expanded.returncode == 0, expanded.stderr
    return [token for token in expanded.stdout.split("\0") if token]


def test_print_command_output_is_paste_safe_for_values_with_spaces() -> None:
    argv = _printed_argv("--version", "v1.2.3 rc1", "--output-dir", "dist")

    assert "run" in argv
    # The value must survive as one argument, not be re-split by the container.
    assert "v1.2.3 rc1" in argv
    assert "rc1" not in argv


def test_build_arguments_are_not_shell_interpolated() -> None:
    # A tag containing a command separator must not become a separate statement
    # inside the container, which has the repository bind-mounted read-write.
    argv = _printed_argv("--version", "v1.0.0; touch /tmp/glibc-guard-probe", "--output-dir", "dist")

    assert "v1.0.0; touch /tmp/glibc-guard-probe" in argv
    assert "touch" not in argv
    assert not any(token.endswith(";") for token in argv)


def test_print_command_honours_image_override() -> None:
    result = _print_command("--image", "quay.io/pypa/manylinux_2_34_x86_64")

    assert result.returncode == 0
    assert "quay.io/pypa/manylinux_2_34_x86_64" in result.stdout


def test_image_override_rejects_non_manylinux_reference() -> None:
    result = _print_command("--image", "ubuntu:22.04")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "--image must be a manylinux_2_<glibc-minor> image" in result.stderr


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


def test_output_dir_outside_repository_exits_2() -> None:
    result = _print_command("--output-dir", "/tmp/outside-repo")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "--output-dir must be a directory inside the repository" in result.stderr


def test_relative_parent_segments_cannot_escape_the_repository() -> None:
    for escape in ("..", "../escape", "dist/../../escape", "."):
        result = _print_command("--output-dir", escape)

        assert result.returncode == 2, f"--output-dir {escape} must be rejected, got: {result.stdout}"
        assert result.stdout == ""
        assert "--output-dir must be a directory inside the repository" in result.stderr


def test_absolute_output_dir_inside_repository_maps_to_container_path() -> None:
    result = _print_command("--output-dir", f"{_to_bash_path(REPO_ROOT)}/dist")

    assert result.returncode == 0
    assert "--output-dir /work/dist" in result.stdout


def test_release_workflow_builds_linux_binary_through_manylinux_script() -> None:
    content = _read(RELEASE_WORKFLOW)

    assert "scripts/build-linux-manylinux.sh" in content
    # The host build that caused #57 must not linger next to the new path.
    assert "bash ./scripts/build.sh --clean" not in content


def test_release_workflow_runs_smokes_on_images_older_than_the_build() -> None:
    workflow = _read(RELEASE_WORKFLOW)
    script = _read(MANYLINUX_SCRIPT)

    # The floor is owned by the build script; the workflow must not duplicate
    # (and silently drift from) that image reference.
    assert "@sha256:" in script
    assert MANYLINUX_IMAGE_TAG not in workflow
    assert SMOKE_IMAGE in workflow
    assert FLOOR_IMAGE in workflow
    # Neither smoke image may be ubuntu-latest (24.04), the image that hid #57.
    assert "ubuntu:24.04" not in workflow
    assert "ubuntu-latest" in workflow  # runners still use it

    for image in (SMOKE_IMAGE, FLOOR_IMAGE):
        # ubuntu:20.04 -> 20, rockylinux:8 -> 8; both must predate 24.04.
        major = int(re.search(r":(\d+)", image).group(1))
        assert major < 24, f"{image} is not older than ubuntu-latest"


def test_release_workflow_smoke_uses_the_older_images_for_linux_binary() -> None:
    content = _read(RELEASE_WORKFLOW)

    linux_smoke_steps = [
        block
        for block in content.split("- name:")
        if "Linux" in block.splitlines()[0]
        and "docker run" in block
        # The backend smoke builds its own LibreOffice image; it is covered by
        # test_release_backend_smoke.py, where the rule is "the built binary runs
        # against a real backend", not "a stock image older than the build".
        and "mid:release-backend-smoke" not in block
    ]

    assert linux_smoke_steps, "Linux smoke steps must run the binary inside a container"
    for block in linux_smoke_steps:
        assert SMOKE_IMAGE in block or FLOOR_IMAGE in block, f"Linux smoke step runs on the wrong image: {block[:80]}"


def test_release_workflow_has_no_dead_build_matrix_script_key() -> None:
    content = _read(RELEASE_WORKFLOW)

    # A leftover `script:` entry documents the host build path #57 removed and
    # invites a later edit that wires it back.
    assert "matrix.script" in content or "script:" not in content


def test_ci_workflow_builds_the_linux_binary_before_release() -> None:
    # release.yml only runs on tags, so the build path needs a pull-request
    # guard; otherwise a broken build script ships unnoticed.
    content = _read(CI_WORKFLOW)

    assert "scripts/build-linux-manylinux.sh" in content
    assert FLOOR_IMAGE in content


def test_ci_workflow_runs_a_real_conversion_on_the_floor_image() -> None:
    content = _read(CI_WORKFLOW)

    # `--version` exits before the converter imports markitdown/magika/
    # onnxruntime, which are what actually pin the glibc floor of the artifact.
    block = content.split("linux-binary:")[1]
    assert "convert" in block, "the PR guard must exercise a real conversion, not only --version"
    assert FLOOR_IMAGE in block


def test_install_smoke_workflow_builds_through_the_manylinux_script() -> None:
    content = _read(INSTALL_SMOKE_WORKFLOW)

    assert "scripts/build-linux-manylinux.sh" in content
    # The Linux leg must not rebuild inline on the runner: that inline build was
    # the second false green of issue #57. The Windows leg keeps its own inline
    # PyInstaller build.
    linux_leg = content.split("Build Windows binary")[0]
    assert "--collect-data magika" not in linux_leg


def test_install_smoke_workflow_triggers_on_the_linux_build_path() -> None:
    content = _read(INSTALL_SMOKE_WORKFLOW)

    assert content.count("scripts/build-linux-manylinux.sh") >= 3  # two path filters + the build step
    assert content.count("scripts/build-constraints.txt") == 0


def test_readme_documents_the_floor_that_the_build_script_claims() -> None:
    readme = _read(README)
    script = _read(MANYLINUX_SCRIPT)

    derived = re.search(r"manylinux_2_(\d+)", script)
    assert derived, "the build script must name its manylinux image"
    floor = f"2.{derived.group(1)}"

    assert "glibc" in readme.lower()
    assert floor in readme
    # Architecture and libc are part of the same compatibility claim.
    assert "x86_64" in readme or "amd64" in readme
    assert "musl" in readme.lower() or "alpine" in readme.lower()


def _readme_section(title: str) -> str:
    readme = _read(README)
    start = readme.index(title)
    rest = readme[start + len(title) :]
    end = rest.find("\n### ")
    return rest if end == -1 else rest[:end]


def test_readme_fallbacks_reference_channels_the_repository_publishes() -> None:
    section = _readme_section("### Linux binary requirements")

    # The project publishes wheels and binaries as GitHub release assets only;
    # it has no PyPI or container-registry publishing step, so the fallback for
    # a blocked user must not point at a name this project does not own.
    assert "pipx install mid" not in section
    assert "pip install --user mid" not in section
    assert "docker run --rm mid" not in section
    assert "releases" in section
    assert "pip install" in section  # the release wheel is still installable


def test_build_script_rejects_missing_mid_build_python_override() -> None:
    result = _run_build_script("--version", "9.9.9", assignments={"MID_BUILD_PYTHON": "/nonexistent/python"})

    assert result.returncode == 2
    assert "MID_BUILD_PYTHON does not point to an executable file" in result.stderr


def test_build_script_rejects_mid_build_python_pointing_at_a_directory() -> None:
    result = _run_build_script("--version", "9.9.9", assignments={"MID_BUILD_PYTHON": "/tmp"})

    assert result.returncode == 2
    assert "MID_BUILD_PYTHON does not point to an executable file" in result.stderr


def test_build_script_preserves_version_mismatch_error_with_override() -> None:
    result = _run_build_script(
        "--version",
        "9.9.9",
        assignments={"MID_BUILD_PYTHON": _to_bash_path(Path(sys.executable))},
    )

    assert result.returncode == 1
    assert "version mismatch" in result.stderr
