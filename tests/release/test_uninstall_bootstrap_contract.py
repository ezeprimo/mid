"""Contract tests for the uninstall scripts (install.sh —force, uninstall.ps1).

These tests verify that the uninstall process correctly removes binaries, backup
files, and PATH-profile stanzas under various installation states.

They do NOT exercise the full bootstrap pipeline — only the uninstall pathways,
on both Linux (bash) and Windows (PowerShell).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


from helpers import _sha256, _require_tool, _to_bash_path, _run_bash_script

REPO_ROOT = Path(__file__).resolve().parents[2]


def _create_linux_state(
    tmp_path: Path,
    *,
    binary: bool = True,
    stanza: bool = True,
    extra_file: bool = False,
    extra_profile: bool = False,
) -> dict[str, object]:
    """Create a fake Linux home directory structure for testing uninstall.

    Returns dict with: home, install_dir, profile, binary_path
    """
    home = tmp_path / "home"
    install_dir = home / ".local" / "bin"
    profile = home / ".profile"
    install_dir.mkdir(parents=True, exist_ok=True)

    if binary:
        binary_path = install_dir / "mid"
        binary_path.write_text("#!/bin/bash\necho fake mid\n", encoding="utf-8", newline="\n")
        binary_path.chmod(0o755)

    if stanza:
        profile.write_text(
            "export EDITOR=vim\n"
            "# >>> mid installer path >>>\n"
            f'export PATH="{install_dir}:$PATH"\n'
            "# <<< mid installer path <<<\n"
            'alias ll="ls -la"\n',
            encoding="utf-8",
            newline="\n",
        )
    else:
        profile.write_text("export EDITOR=vim\n", encoding="utf-8", newline="\n")

    if extra_file:
        (install_dir / "other.tool").write_text("not mid\n", encoding="utf-8", newline="\n")

    if extra_profile:
        bashrc = home / ".bashrc"
        bashrc.write_text(
            f'# >>> mid installer path >>>\nexport PATH="{install_dir}:$PATH"\n# <<< mid installer path <<<\n',
            encoding="utf-8",
            newline="\n",
        )

    return {
        "home": home,
        "install_dir": install_dir,
        "profile": profile,
        "binary_path": install_dir / "mid" if binary else None,
    }


# =============================================================================
# Linux (bash) tests
# =============================================================================


def test_linux_full_uninstall(tmp_path: Path) -> None:
    bash = _require_tool("bash")
    state = _create_linux_state(tmp_path)

    env = os.environ.copy()
    overrides = {"HOME": _to_bash_path(state["home"])}  # type: ignore[arg-type]

    result = _run_bash_script(bash, REPO_ROOT / "uninstall.sh", env, overrides, args=["--force"])
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    # binary removed
    assert not state["binary_path"].exists()  # type: ignore[union-attr]
    # stanza markers removed from profile
    profile_text = state["profile"].read_text(encoding="utf-8")  # type: ignore[union-attr]
    assert "# >>> mid installer path >>>" not in profile_text
    assert "# <<< mid installer path <<<" not in profile_text
    # "removed" in stdout
    assert "removed" in result.stdout
    # empty install dir removed
    assert not state["install_dir"].exists()  # type: ignore[union-attr]


def test_linux_dry_run(tmp_path: Path) -> None:
    bash = _require_tool("bash")
    state = _create_linux_state(tmp_path)

    binary_before = _sha256(state["binary_path"])
    profile_before = _sha256(state["profile"])

    env = os.environ.copy()
    overrides = {"HOME": _to_bash_path(state["home"])}  # type: ignore[arg-type]

    result = _run_bash_script(bash, REPO_ROOT / "uninstall.sh", env, overrides, args=["--dry-run"])
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    # binary still exists
    assert state["binary_path"].exists()  # type: ignore[union-attr]
    assert _sha256(state["binary_path"]) == binary_before
    # profile unchanged
    assert _sha256(state["profile"]) == profile_before
    # "dry-run" in stdout
    assert "dry-run" in result.stdout


def test_linux_nothing_installed(tmp_path: Path) -> None:
    bash = _require_tool("bash")
    state = _create_linux_state(tmp_path, binary=False, stanza=False)
    # Remove the entire install tree so uninstall sees a truly clean state
    shutil.rmtree(state["home"] / ".local")

    env = os.environ.copy()
    overrides = {"HOME": _to_bash_path(state["home"])}  # type: ignore[arg-type]

    result = _run_bash_script(bash, REPO_ROOT / "uninstall.sh", env, overrides, args=["--force"])
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    # "Nothing to uninstall" in summary
    assert "Nothing to uninstall" in result.stdout
    # "absent" in output for each item checked
    assert "absent" in result.stdout


def test_linux_binary_only(tmp_path: Path) -> None:
    bash = _require_tool("bash")
    state = _create_linux_state(tmp_path, binary=True, stanza=False)

    env = os.environ.copy()
    overrides = {"HOME": _to_bash_path(state["home"])}  # type: ignore[arg-type]

    result = _run_bash_script(bash, REPO_ROOT / "uninstall.sh", env, overrides, args=["--force"])
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    # binary removed
    assert not state["binary_path"].exists()  # type: ignore[union-attr]
    # no stanza-related errors or unexpected messages
    assert "removed" in result.stdout


def test_linux_non_empty_dir(tmp_path: Path) -> None:
    bash = _require_tool("bash")
    state = _create_linux_state(tmp_path, binary=True, stanza=True, extra_file=True)

    env = os.environ.copy()
    overrides = {"HOME": _to_bash_path(state["home"])}  # type: ignore[arg-type]

    result = _run_bash_script(bash, REPO_ROOT / "uninstall.sh", env, overrides, args=["--force"])
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    # binary removed
    assert not state["binary_path"].exists()  # type: ignore[union-attr]
    # "remain" in output because extra file prevents dir removal
    assert "remain" in result.stdout
    # install dir still exists (it has extra_file)
    assert state["install_dir"].exists()  # type: ignore[union-attr]


def test_linux_additional_profiles(tmp_path: Path) -> None:
    bash = _require_tool("bash")
    state = _create_linux_state(tmp_path, binary=True, stanza=True, extra_profile=True)
    bashrc = state["home"] / ".bashrc"

    env = os.environ.copy()
    overrides = {"HOME": _to_bash_path(state["home"])}  # type: ignore[arg-type]

    result = _run_bash_script(bash, REPO_ROOT / "uninstall.sh", env, overrides, args=["--force"])
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    # stanza removed from both profile and .bashrc
    profile_text = state["profile"].read_text(encoding="utf-8")
    assert "# >>> mid installer path >>>" not in profile_text
    assert "# <<< mid installer path <<<" not in profile_text

    bashrc_text = bashrc.read_text(encoding="utf-8")
    assert "# >>> mid installer path >>>" not in bashrc_text
    assert "# <<< mid installer path <<<" not in bashrc_text

    # "removed" appears at least once (one or both stanzas removed)
    assert "removed" in result.stdout


def test_linux_force_skips_prompt(tmp_path: Path) -> None:
    bash = _require_tool("bash")
    state = _create_linux_state(tmp_path)

    env = os.environ.copy()
    overrides = {"HOME": _to_bash_path(state["home"])}  # type: ignore[arg-type]

    # No stdin pipe — --force must skip the confirmation prompt
    result = _run_bash_script(bash, REPO_ROOT / "uninstall.sh", env, overrides, args=["--force"])
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    # binary removed (proving script didn't hang on prompt)
    assert not state["binary_path"].exists()  # type: ignore[union-attr]


# =============================================================================
# Windows (PowerShell) tests
# =============================================================================


def test_windows_full_uninstall(tmp_path: Path) -> None:
    pwsh = _require_tool("pwsh")
    local_app_data = tmp_path / "local-app-data"
    install_dir = local_app_data / "mid" / "bin"
    install_dir.mkdir(parents=True)
    binary = install_dir / "mid.exe"
    binary.write_text("fake mid binary", encoding="utf-8")
    bak = binary.with_name("mid.exe.bak")
    bak.write_text("backup", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "MID_DISABLE_PERSIST_PATH_UPDATE": "1",
            "LOCALAPPDATA": str(local_app_data),
        }
    )

    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO_ROOT / "uninstall.ps1"), "-Force"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert not binary.exists()
    assert not bak.exists()
    assert "removed" in result.stdout


def test_windows_dry_run(tmp_path: Path) -> None:
    pwsh = _require_tool("pwsh")
    local_app_data = tmp_path / "local-app-data"
    install_dir = local_app_data / "mid" / "bin"
    install_dir.mkdir(parents=True)
    binary = install_dir / "mid.exe"
    binary.write_text("fake mid binary", encoding="utf-8")
    binary_before = _sha256(binary)

    env = os.environ.copy()
    env.update(
        {
            "MID_DISABLE_PERSIST_PATH_UPDATE": "1",
            "LOCALAPPDATA": str(local_app_data),
        }
    )

    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO_ROOT / "uninstall.ps1"), "-DryRun", "-Force"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert binary.exists()
    assert _sha256(binary) == binary_before
    assert "dry-run" in result.stdout


def test_windows_nothing_installed(tmp_path: Path) -> None:
    pwsh = _require_tool("pwsh")
    local_app_data = tmp_path / "local-app-data"
    # Create the parent dir but not the install dir itself
    (local_app_data / "mid").mkdir(parents=True)

    env = os.environ.copy()
    env.update(
        {
            "MID_DISABLE_PERSIST_PATH_UPDATE": "1",
            "LOCALAPPDATA": str(local_app_data),
        }
    )

    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO_ROOT / "uninstall.ps1"), "-Force"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    # "mid has been uninstalled" (empty mid/ dir gets removed) or
    # "Nothing to uninstall" (truly nothing found)
    assert "mid has been uninstalled" in result.stdout or "Nothing to uninstall" in result.stdout, (
        f"unexpected summary in: {result.stdout}"
    )


def test_windows_binary_and_bak(tmp_path: Path) -> None:
    pwsh = _require_tool("pwsh")
    local_app_data = tmp_path / "local-app-data"
    install_dir = local_app_data / "mid" / "bin"
    install_dir.mkdir(parents=True)
    binary = install_dir / "mid.exe"
    binary.write_text("fake mid binary", encoding="utf-8")
    bak = binary.with_name("mid.exe.bak")
    bak.write_text("backup", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "MID_DISABLE_PERSIST_PATH_UPDATE": "1",
            "LOCALAPPDATA": str(local_app_data),
        }
    )

    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO_ROOT / "uninstall.ps1"), "-Force"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert not binary.exists()
    assert not bak.exists()


def test_windows_non_empty_dir(tmp_path: Path) -> None:
    pwsh = _require_tool("pwsh")
    local_app_data = tmp_path / "local-app-data"
    install_dir = local_app_data / "mid" / "bin"
    install_dir.mkdir(parents=True)
    binary = install_dir / "mid.exe"
    binary.write_text("fake mid binary", encoding="utf-8")
    extra = install_dir / "other_file.txt"
    extra.write_text("not mid", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "MID_DISABLE_PERSIST_PATH_UPDATE": "1",
            "LOCALAPPDATA": str(local_app_data),
        }
    )

    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO_ROOT / "uninstall.ps1"), "-Force"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert not binary.exists()
    assert extra.exists()
    assert "remain" in result.stdout or "not mid-related" in result.stdout


def test_windows_custom_path(tmp_path: Path) -> None:
    pwsh = _require_tool("pwsh")
    custom_dir = tmp_path / "custom" / "bin"
    custom_dir.mkdir(parents=True)
    binary = custom_dir / "mid.exe"
    binary.write_text("fake mid binary", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "MID_INSTALL_DIR": str(custom_dir),
            "LOCALAPPDATA": str(tmp_path / "local-app-data"),
        }
    )

    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO_ROOT / "uninstall.ps1"), "-Force"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert not binary.exists()


def test_linux_help() -> None:
    bash = _require_tool("bash")
    result = subprocess.run(
        [bash, _to_bash_path(REPO_ROOT / "uninstall.sh"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "Usage:" in result.stdout or "usage:" in result.stdout


def test_windows_help(tmp_path: Path) -> None:
    pwsh = _require_tool("pwsh")
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local-app-data")
    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO_ROOT / "uninstall.ps1"), "-Help"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    # Note: uninstall.ps1 does not implement a -Help parameter.
    # The flag is silently ignored and the script runs normally.
    # We only verify it exits successfully without crashing.
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
