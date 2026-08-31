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


def _create_cache_files(home: Path, xdg_cache: Path | None = None, xdg_config: Path | None = None) -> list[Path]:
    """Create update-checker cache files mirroring uninstall.sh candidates.

    Mirrors ``uninstall.sh`` logic exactly::

        "${XDG_CACHE_HOME:-$HOME/.cache}/mid/update_cache.json"
        "$HOME/.cache/mid/update_cache.json"
        "$HOME/Library/Caches/mid/update_cache.json"
        "${XDG_CONFIG_HOME:-$HOME/.config}/mid/.update_cache.json"
        "$HOME/.config/mid/.update_cache.json"
        "$HOME/.config/mid/update_cache.json"

    Deduplicates like the script and returns the list of distinct Paths created.
    Each file contains minimal valid JSON (latest_version + checked_at).
    """

    candidates: list[Path] = []
    effective_cache = xdg_cache if xdg_cache is not None else home / ".cache"
    candidates.append(effective_cache / "mid" / "update_cache.json")
    candidates.append(home / ".cache" / "mid" / "update_cache.json")
    candidates.append(home / "Library" / "Caches" / "mid" / "update_cache.json")
    effective_config = xdg_config if xdg_config is not None else home / ".config"
    candidates.append(effective_config / "mid" / ".update_cache.json")
    candidates.append(home / ".config" / "mid" / ".update_cache.json")
    candidates.append(home / ".config" / "mid" / "update_cache.json")

    seen: set[Path] = set()
    created: list[Path] = []
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        cand.parent.mkdir(parents=True, exist_ok=True)
        cand.write_text(
            '{"latest_version": "9.9.9", "checked_at": "2026-01-01T00:00:00Z"}',
            encoding="utf-8",
        )
        created.append(cand)
    return created


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


# =============================================================================
# Linux — update checker cache cleanup
# =============================================================================


def test_linux_update_cache_dry_run(tmp_path: Path) -> None:
    """Dry-run must report cache cleanup without deleting files."""
    bash = _require_tool("bash")
    state = _create_linux_state(tmp_path)
    home = state["home"]  # type: ignore[assignment]
    cache_files = _create_cache_files(home)  # type: ignore[arg-type]
    assert len(cache_files) >= 2, "helper should create at least 2 distinct cache files"
    for p in cache_files:
        assert p.exists(), f"cache file not created: {p}"

    hashes_before = {p: _sha256(p) for p in cache_files}
    binary_before = _sha256(state["binary_path"])  # type: ignore[arg-type]
    profile_before = _sha256(state["profile"])  # type: ignore[arg-type]

    env = os.environ.copy()
    overrides = {"HOME": _to_bash_path(home)}  # type: ignore[arg-type]

    result = _run_bash_script(bash, REPO_ROOT / "uninstall.sh", env, overrides, args=["--dry-run"])
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    stdout_lower = result.stdout.lower()
    assert "update checker cache" in stdout_lower, f"missing 'update checker cache' in: {result.stdout}"
    assert "dry-run" in stdout_lower, f"missing 'dry-run' in: {result.stdout}"
    assert "update_cache.json" in result.stdout, f"missing 'update_cache.json' in: {result.stdout}"

    # each candidate file still exists and is unchanged
    for p in cache_files:
        assert p.exists(), f"dry-run should not delete {p}"
        assert _sha256(p) == hashes_before[p], f"dry-run modified {p}"

    # binary and profile unchanged (reuse existing pattern)
    assert state["binary_path"].exists()  # type: ignore[union-attr]
    assert _sha256(state["binary_path"]) == binary_before  # type: ignore[arg-type]
    assert _sha256(state["profile"]) == profile_before  # type: ignore[arg-type]

    # dry output mentions each existing candidate (at least 2 expected)
    dry_cache_lines = [ln for ln in result.stdout.splitlines() if "dry-run" in ln.lower() and "update_cache.json" in ln]
    assert len(dry_cache_lines) >= 2, (
        f"expected at least 2 dry-run cache lines, got {len(dry_cache_lines)}: {dry_cache_lines}\nstdout:\n{result.stdout}"
    )


def test_linux_update_cache_removed_on_force(tmp_path: Path) -> None:
    """--force must delete cache files and remove empty parents."""
    bash = _require_tool("bash")
    state = _create_linux_state(tmp_path)
    home = state["home"]  # type: ignore[assignment]
    cache_files = _create_cache_files(home)  # type: ignore[arg-type]
    assert len(cache_files) >= 2
    for p in cache_files:
        assert p.exists()

    env = os.environ.copy()
    overrides = {"HOME": _to_bash_path(home)}  # type: ignore[arg-type]

    result = _run_bash_script(bash, REPO_ROOT / "uninstall.sh", env, overrides, args=["--force"])
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    stdout_lower = result.stdout.lower()
    assert "removed" in stdout_lower, f"missing 'removed' in: {result.stdout}"
    assert "update checker cache" in stdout_lower
    assert "update_cache.json" in result.stdout

    for p in cache_files:
        assert not p.exists(), f"expected {p} to be deleted"

    # empty parent dirs removed (script does rmdir bottom-up, best-effort)
    assert not (home / ".cache" / "mid").exists(), "expected .cache/mid to be removed when empty"
    assert not (home / ".config" / "mid").exists(), "expected .config/mid to be removed when empty"
    assert not (home / "Library" / "Caches" / "mid").exists(), "expected Library/Caches/mid to be removed when empty"


def test_linux_update_cache_non_empty_parent_kept(tmp_path: Path) -> None:
    """Parent dir with extra file must be kept after cache cleanup."""
    bash = _require_tool("bash")
    state = _create_linux_state(tmp_path)
    home = state["home"]  # type: ignore[assignment]
    cache_files = _create_cache_files(home)  # type: ignore[arg-type]

    keep = home / ".config" / "mid" / "keep.txt"  # type: ignore[union-attr]
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_text("keep me", encoding="utf-8")

    for p in cache_files:
        assert p.exists()
    assert keep.exists()

    env = os.environ.copy()
    overrides = {"HOME": _to_bash_path(home)}  # type: ignore[arg-type]

    result = _run_bash_script(bash, REPO_ROOT / "uninstall.sh", env, overrides, args=["--force"])
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    for p in cache_files:
        assert not p.exists(), f"cache file {p} should be deleted"

    assert keep.exists(), "keep.txt should not be deleted"
    assert (home / ".config" / "mid").exists(), "parent should be kept when non-empty"
    # other empty parents still removed
    assert not (home / ".cache" / "mid").exists()  # type: ignore[union-attr]
    assert not (home / "Library" / "Caches" / "mid").exists()  # type: ignore[union-attr]


def test_linux_update_cache_xdg_overrides(tmp_path: Path) -> None:
    """XDG_CACHE_HOME / XDG_CONFIG_HOME overrides must be respected."""
    bash = _require_tool("bash")
    state = _create_linux_state(tmp_path)
    home = state["home"]  # type: ignore[assignment]

    xdg_cache = tmp_path / "custom_cache"
    xdg_config = tmp_path / "custom_config"

    cache_files = _create_cache_files(home, xdg_cache=xdg_cache, xdg_config=xdg_config)  # type: ignore[arg-type]

    custom_cache_file = xdg_cache / "mid" / "update_cache.json"
    custom_config_file = xdg_config / "mid" / ".update_cache.json"
    assert custom_cache_file.exists(), f"custom cache file not created: {custom_cache_file}"
    assert custom_config_file.exists(), f"custom config file not created: {custom_config_file}"

    env = os.environ.copy()
    overrides = {
        "HOME": _to_bash_path(home),  # type: ignore[arg-type]
        "XDG_CACHE_HOME": _to_bash_path(xdg_cache),
        "XDG_CONFIG_HOME": _to_bash_path(xdg_config),
    }

    result = _run_bash_script(bash, REPO_ROOT / "uninstall.sh", env, overrides, args=["--force"])
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    stdout_lower = result.stdout.lower()
    assert "removed" in stdout_lower
    assert "update checker cache" in stdout_lower

    assert not custom_cache_file.exists(), "custom XDG cache file should be deleted"
    assert not custom_config_file.exists(), "custom XDG config file should be deleted"
    # parents of custom locations should be removed if empty (best-effort)
    assert not (xdg_cache / "mid").exists(), "custom cache parent should be removed when empty"
    assert not (xdg_config / "mid").exists(), "custom config parent should be removed when empty"

    # all cache files (including home fallbacks) must be gone
    for p in cache_files:
        assert not p.exists(), f"expected {p} to be deleted"


# =============================================================================
# Windows — update checker cache cleanup (PowerShell)
# =============================================================================


def test_windows_update_cache_dry_run(tmp_path: Path) -> None:
    """Windows dry-run must report cache cleanup without deleting files."""
    pwsh = _require_tool("pwsh")
    local_app_data = tmp_path / "local-app-data"
    home = tmp_path / "home"
    install_dir = local_app_data / "mid" / "bin"
    install_dir.mkdir(parents=True)
    binary = install_dir / "mid.exe"
    binary.write_text("fake mid binary", encoding="utf-8")
    binary_before = _sha256(binary)

    candidates: list[Path] = []
    p1 = local_app_data / "mid" / "update_cache.json"
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_text('{"latest_version": "9.9.9"}', encoding="utf-8")
    candidates.append(p1)
    p2 = home / ".cache" / "mid" / "update_cache.json"
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_text("{}", encoding="utf-8")
    candidates.append(p2)
    p3 = home / ".config" / "mid" / ".update_cache.json"
    p3.parent.mkdir(parents=True, exist_ok=True)
    p3.write_text("{}", encoding="utf-8")
    candidates.append(p3)
    p4 = home / ".config" / "mid" / "update_cache.json"
    p4.write_text("{}", encoding="utf-8")
    candidates.append(p4)
    p5 = home / "Library" / "Caches" / "mid" / "update_cache.json"
    p5.parent.mkdir(parents=True, exist_ok=True)
    p5.write_text("{}", encoding="utf-8")
    candidates.append(p5)

    hashes_before = {p: _sha256(p) for p in candidates}
    for p in candidates:
        assert p.exists()

    env = os.environ.copy()
    env.update(
        {
            "MID_DISABLE_PERSIST_PATH_UPDATE": "1",
            "LOCALAPPDATA": str(local_app_data),
            "HOME": str(home),
            "USERPROFILE": str(home),
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
    for p in candidates:
        assert p.exists(), f"dry-run should not delete {p}"
        assert _sha256(p) == hashes_before[p]

    stdout_lower = result.stdout.lower()
    assert "dry-run" in stdout_lower
    assert "update checker cache" in stdout_lower
    assert "update_cache.json" in result.stdout
    dry_lines = [ln for ln in result.stdout.splitlines() if "dry-run" in ln.lower() and "update_cache.json" in ln]
    assert len(dry_lines) >= 2, f"expected >=2 dry-run cache lines, got {dry_lines}\nstdout:\n{result.stdout}"


def test_windows_update_cache_removed_on_force(tmp_path: Path) -> None:
    """Windows --force must delete cache files."""
    pwsh = _require_tool("pwsh")
    local_app_data = tmp_path / "local-app-data"
    home = tmp_path / "home"
    install_dir = local_app_data / "mid" / "bin"
    install_dir.mkdir(parents=True)
    binary = install_dir / "mid.exe"
    binary.write_text("fake mid binary", encoding="utf-8")

    candidates: list[Path] = []
    p1 = local_app_data / "mid" / "update_cache.json"
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_text("{}", encoding="utf-8")
    candidates.append(p1)
    p2 = home / ".cache" / "mid" / "update_cache.json"
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_text("{}", encoding="utf-8")
    candidates.append(p2)
    p3 = home / ".config" / "mid" / ".update_cache.json"
    p3.parent.mkdir(parents=True, exist_ok=True)
    p3.write_text("{}", encoding="utf-8")
    candidates.append(p3)
    p4 = home / ".config" / "mid" / "update_cache.json"
    p4.write_text("{}", encoding="utf-8")
    candidates.append(p4)
    p5 = home / "Library" / "Caches" / "mid" / "update_cache.json"
    p5.parent.mkdir(parents=True, exist_ok=True)
    p5.write_text("{}", encoding="utf-8")
    candidates.append(p5)

    for p in candidates:
        assert p.exists()

    env = os.environ.copy()
    env.update(
        {
            "MID_DISABLE_PERSIST_PATH_UPDATE": "1",
            "LOCALAPPDATA": str(local_app_data),
            "HOME": str(home),
            "USERPROFILE": str(home),
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
    stdout_lower = result.stdout.lower()
    assert "removed" in stdout_lower
    assert "update checker cache" in stdout_lower
    assert "update_cache.json" in result.stdout
    for p in candidates:
        assert not p.exists(), f"expected {p} to be deleted"

    # home-based parents that were exclusive should be gone when empty
    assert not (home / ".cache" / "mid").exists()
    assert not (home / "Library" / "Caches" / "mid").exists()
    # .config/mid had two files both removed -> should be gone
    assert not (home / ".config" / "mid").exists()


def test_windows_update_cache_custom_xdg(tmp_path: Path) -> None:
    """Windows must respect XDG_CACHE_HOME / XDG_CONFIG_HOME overrides."""
    pwsh = _require_tool("pwsh")
    local_app_data = tmp_path / "local-app-data"
    home = tmp_path / "home"
    xdg_cache = tmp_path / "custom_cache"
    xdg_config = tmp_path / "custom_config"

    # custom XDG candidates
    custom_cache_file = xdg_cache / "mid" / "update_cache.json"
    custom_cache_file.parent.mkdir(parents=True, exist_ok=True)
    custom_cache_file.write_text("{}", encoding="utf-8")
    custom_config_dot = xdg_config / "mid" / ".update_cache.json"
    custom_config_dot.parent.mkdir(parents=True, exist_ok=True)
    custom_config_dot.write_text("{}", encoding="utf-8")
    custom_config_legacy = xdg_config / "mid" / "update_cache.json"
    custom_config_legacy.write_text("{}", encoding="utf-8")

    # also create a default HOME cache to ensure both are cleaned
    default_cache = home / ".cache" / "mid" / "update_cache.json"
    default_cache.parent.mkdir(parents=True, exist_ok=True)
    default_cache.write_text("{}", encoding="utf-8")

    for p in [custom_cache_file, custom_config_dot, custom_config_legacy, default_cache]:
        assert p.exists()

    env = os.environ.copy()
    env.update(
        {
            "MID_DISABLE_PERSIST_PATH_UPDATE": "1",
            "LOCALAPPDATA": str(local_app_data),
            "HOME": str(home),
            "USERPROFILE": str(home),
            "XDG_CACHE_HOME": str(xdg_cache),
            "XDG_CONFIG_HOME": str(xdg_config),
        }
    )

    # ensure LOCALAPPDATA parent exists to avoid LOCALAPPDATA error
    (local_app_data / "mid").mkdir(parents=True, exist_ok=True)

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
    stdout_lower = result.stdout.lower()
    assert "removed" in stdout_lower
    assert "update checker cache" in stdout_lower

    assert not custom_cache_file.exists(), "custom XDG cache file should be deleted"
    assert not custom_config_dot.exists()
    assert not custom_config_legacy.exists()
    assert not default_cache.exists()
    assert not (xdg_cache / "mid").exists()
    assert not (xdg_config / "mid").exists()


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
