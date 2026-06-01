from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_linux_build_script_bundles_runtime_conversion_dependencies() -> None:
    content = _read("scripts/build.sh")

    assert "--hidden-import markitdown" in content
    assert "--collect-data magika" in content
    assert "--exclude-module onnxruntime" not in content


def test_windows_build_script_bundles_runtime_conversion_dependencies() -> None:
    content = _read("scripts/build.ps1")

    assert '"--hidden-import", "markitdown"' in content
    assert '"--collect-data", "magika"' in content
    assert '"--exclude-module", "onnxruntime"' not in content


def test_windows_build_script_uses_python_module_invocation_for_pyinstaller() -> None:
    content = _read("scripts/build.ps1")

    assert "Get-Command pyinstaller" not in content
    assert "-m PyInstaller" in content
