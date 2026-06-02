from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

from scripts.release.validate_release import resolve_release_tag


REPO_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_ASSET = "mid-windows-amd64.exe"
LINUX_ASSET = "mid-linux-amd64"
CHECKSUMS_ASSET = "checksums.txt"


@dataclass(frozen=True)
class WindowsHarness:
    base_url: str
    repo: str
    tag: str
    windows_hash: str


@dataclass(frozen=True)
class LinuxHarness:
    api_base: str
    repo: str
    latest_tag: str
    hashes_by_tag: dict[str, str]


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
    bash: str, script: Path, env: dict[str, str], overrides: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    exports = "; ".join(f"export {key}={shlex.quote(value)}" for key, value in sorted(overrides.items()))
    command = (
        f"{exports}; exec bash {shlex.quote(_to_bash_path(script))}"
        if exports
        else f"exec bash {shlex.quote(_to_bash_path(script))}"
    )
    return subprocess.run([bash, "-lc", command], cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)


def _write_linux_stub(path: Path, tag: str) -> None:
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'if [[ "${1:-}" == "--version" ]]; then',
                f'  echo "mid {tag}"',
                "  exit 0",
                "fi",
                'echo "mid test binary"',
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    path.chmod(0o755)


@pytest.fixture
def windows_release_harness(tmp_path: Path) -> WindowsHarness:
    repo = "fixture/mid"
    tag = "v1.2.3"

    pwsh_path = Path(_require_tool("pwsh"))
    asset_dir = tmp_path / "windows-assets"
    asset_dir.mkdir(parents=True, exist_ok=True)

    windows_binary = asset_dir / WINDOWS_ASSET
    shutil.copy2(pwsh_path, windows_binary)
    checksums = asset_dir / CHECKSUMS_ASSET
    checksums.write_text(f"{_sha256(windows_binary)}  {WINDOWS_ASSET}\n", encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            host, port = self.server.server_address
            base = f"http://{host}:{port}"
            if path in {f"/repos/{repo}/releases/latest", f"/repos/{repo}/releases/tags/{tag}"}:
                payload = {
                    "tag_name": tag,
                    "draft": False,
                    "prerelease": False,
                    "assets": [
                        {"name": WINDOWS_ASSET, "browser_download_url": f"{base}/assets/{WINDOWS_ASSET}"},
                        {"name": CHECKSUMS_ASSET, "browser_download_url": f"{base}/assets/{CHECKSUMS_ASSET}"},
                    ],
                }
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == f"/assets/{WINDOWS_ASSET}":
                payload = windows_binary.read_bytes()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            if path == f"/assets/{CHECKSUMS_ASSET}":
                payload = checksums.read_bytes()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            self.send_response(404)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        yield WindowsHarness(
            base_url=f"http://{host}:{port}",
            repo=repo,
            tag=tag,
            windows_hash=_sha256(windows_binary),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def linux_release_harness(tmp_path: Path) -> LinuxHarness:
    repo = "fixture/mid"
    latest_tag = "v1.2.3"
    tags = ("v1.2.3", "v1.2.2", "v1.2.4")

    api_root = tmp_path / "linux-api"
    tags_dir = api_root / "repos" / "fixture" / "mid" / "releases" / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)

    hashes_by_tag: dict[str, str] = {}
    for tag in tags:
        asset_dir = tmp_path / "linux-assets" / tag
        asset_dir.mkdir(parents=True, exist_ok=True)
        binary = asset_dir / LINUX_ASSET
        _write_linux_stub(binary, tag)
        binary_hash = _sha256(binary)
        hashes_by_tag[tag] = binary_hash

        checksums_hash = binary_hash if tag != "v1.2.4" else "0" * 64
        checksums = asset_dir / CHECKSUMS_ASSET
        checksums.write_text(f"{checksums_hash}  {LINUX_ASSET}\n", encoding="utf-8")

        release_payload = {
            "tag_name": tag,
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": LINUX_ASSET, "browser_download_url": f"file://{_to_bash_path(binary)}"},
                {"name": CHECKSUMS_ASSET, "browser_download_url": f"file://{_to_bash_path(checksums)}"},
            ],
        }
        (tags_dir / tag).write_text(json.dumps(release_payload), encoding="utf-8")

    latest_payload = json.loads((tags_dir / latest_tag).read_text(encoding="utf-8"))
    (api_root / "repos" / "fixture" / "mid" / "releases" / "latest").write_text(json.dumps(latest_payload), encoding="utf-8")

    return LinuxHarness(
        api_base=f"file://{_to_bash_path(api_root)}",
        repo=repo,
        latest_tag=latest_tag,
        hashes_by_tag=hashes_by_tag,
    )


def test_version_resolution_is_deterministic_for_latest_and_pinned() -> None:
    stable = {"tag_name": "v1.2.3", "draft": False, "prerelease": False}
    prerelease = {"tag_name": "v1.3.0", "draft": False, "prerelease": True}

    assert resolve_release_tag("latest", [stable, prerelease]) == "v1.2.3"
    assert resolve_release_tag("v1.2.3", [stable, prerelease]) == "v1.2.3"


def test_windows_bootstrap_installs_to_user_local_path(windows_release_harness: WindowsHarness, tmp_path: Path) -> None:
    pwsh = _require_tool("pwsh")
    local_app_data = tmp_path / "local-app-data"

    env = os.environ.copy()
    env.update(
        {
            "MID_REPO": windows_release_harness.repo,
            "MID_API_BASE": windows_release_harness.base_url,
            "MID_RAW_BASE": windows_release_harness.base_url,
            "MID_DISABLE_PERSIST_PATH_UPDATE": "1",
            "MID_SMOKE_PATTERN": ".",
            "LOCALAPPDATA": str(local_app_data),
            "MID_VERSION": windows_release_harness.tag,
        }
    )

    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO_ROOT / "install.ps1")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    installed = local_app_data / "mid" / "bin" / "mid.exe"
    assert installed.exists()
    assert _sha256(installed) == windows_release_harness.windows_hash
    assert "Persistent PATH update disabled via MID_DISABLE_PERSIST_PATH_UPDATE" in result.stdout


def test_linux_bootstrap_and_rollback_runtime_coverage(linux_release_harness: LinuxHarness, tmp_path: Path) -> None:
    bash = _require_tool("bash")
    _require_bash_command(bash, "curl")
    _require_bash_command(bash, "sha256sum")
    _require_bash_command(bash, "python3")

    home = tmp_path / "linux-home"
    common_env = os.environ.copy()
    overrides = {
        "MID_REPO": linux_release_harness.repo,
        "MID_API_BASE": linux_release_harness.api_base,
        "MID_RAW_BASE": linux_release_harness.api_base,
        "MID_PYTHON_BIN": "python3",
        "HOME": _to_bash_path(home),
    }

    latest = _run_bash_script(
        bash,
        REPO_ROOT / "install.sh",
        common_env,
        {**overrides, "MID_VERSION": linux_release_harness.latest_tag},
    )
    assert latest.returncode == 0, f"stdout:\n{latest.stdout}\n\nstderr:\n{latest.stderr}"

    installed = home / ".local" / "bin" / "mid"
    assert installed.exists()
    assert _sha256(installed) == linux_release_harness.hashes_by_tag["v1.2.3"]

    rollback = _run_bash_script(
        bash,
        REPO_ROOT / "install.sh",
        common_env,
        {**overrides, "MID_VERSION": "v1.2.2"},
    )
    assert rollback.returncode == 0, f"stdout:\n{rollback.stdout}\n\nstderr:\n{rollback.stderr}"
    assert _sha256(installed) == linux_release_harness.hashes_by_tag["v1.2.2"]
    assert _sha256(installed) != linux_release_harness.hashes_by_tag["v1.2.3"]

    version_check = subprocess.run(
        [bash, "-lc", f'"{_to_bash_path(installed)}" --version'],
        cwd=REPO_ROOT,
        env=common_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert version_check.returncode == 0
    assert "mid v1.2.2" in version_check.stdout


def test_linux_integrity_and_path_failure_guidance_is_executed(linux_release_harness: LinuxHarness, tmp_path: Path) -> None:
    bash = _require_tool("bash")
    _require_bash_command(bash, "curl")
    _require_bash_command(bash, "sha256sum")
    _require_bash_command(bash, "python3")

    home = tmp_path / "linux-guidance-home"
    common_env = os.environ.copy()
    overrides = {
        "MID_REPO": linux_release_harness.repo,
        "MID_API_BASE": linux_release_harness.api_base,
        "MID_RAW_BASE": linux_release_harness.api_base,
        "MID_PYTHON_BIN": "python3",
        "HOME": _to_bash_path(home),
    }

    integrity_fail = _run_bash_script(
        bash,
        REPO_ROOT / "install.sh",
        common_env,
        {**overrides, "MID_VERSION": "v1.2.4"},
    )
    assert integrity_fail.returncode != 0
    assert "SHA-256 mismatch for mid-linux-amd64" in integrity_fail.stderr
    assert "pipx install --force 'mid==1.2.4'" in integrity_fail.stdout

    path_guidance = _run_bash_script(
        bash,
        REPO_ROOT / "install.sh",
        common_env,
        {
            **overrides,
            "MID_VERSION": linux_release_harness.latest_tag,
            "MID_DISABLE_PERSIST_PATH_UPDATE": "1",
        },
    )
    assert path_guidance.returncode == 0, f"stdout:\n{path_guidance.stdout}\n\nstderr:\n{path_guidance.stderr}"
    assert "Could not update" not in path_guidance.stderr
    assert "Add this line manually and open a new shell" not in path_guidance.stderr
    assert "mid" in path_guidance.stdout  # verify install still succeeded
