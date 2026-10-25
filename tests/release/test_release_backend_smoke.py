"""Contract tests for the release backend smoke (issue #65).

v0.5.0 shipped a Linux binary whose LibreOffice detection was broken: the
PyInstaller bundle exported ``LD_LIBRARY_PATH`` and the spawned ``soffice``
resolved the bundle's older libraries. Every CI job stayed green because the
release smoke converted a ``.docx`` (native path) and never probed a backend.

These tests pin the step that exercises a real backend on the *built* binary.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
LEGACY_DOCKERFILE = REPO_ROOT / "docker" / "Dockerfile.legacy"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _backend_smoke_block() -> str:
    content = _read(RELEASE_WORKFLOW)
    marker = "- name: Smoke backend probe and ODF conversion"
    assert marker in content, "the release workflow must run a backend smoke"
    return content.split(marker, 1)[1]


def test_release_workflow_builds_the_libreoffice_image_for_the_smoke() -> None:
    content = _read(RELEASE_WORKFLOW)

    assert LEGACY_DOCKERFILE.is_file()
    # Reuse the project's LibreOffice image instead of inventing a second one, so
    # the smoke runs against the pinned package set the project documents.
    assert "docker build -f docker/Dockerfile.legacy -t mid:release-backend-smoke ." in content


def test_backend_smoke_runs_the_built_binary_not_the_image_copy() -> None:
    block = _backend_smoke_block()

    # The image also contains its own `mid`; using that one would prove nothing
    # about the artifact being released.
    assert "/dist/mid-linux-amd64" in block
    assert "\n              mid " not in block


def test_backend_smoke_asserts_probe_doctor_and_routing() -> None:
    block = _backend_smoke_block()

    assert "--list-backends" in block
    assert "libreoffice: available" in block
    assert "backend:libreoffice: ok" in block
    # Auto-routing: the .odt must convert WITHOUT --backend, which is exactly
    # what was broken in v0.5.0.
    assert "convert /smoke/seed.odt -o /smoke/out.md" in block
    assert "--backend libreoffice /smoke/seed.odt" not in block


def test_backend_smoke_produces_a_real_odt_with_libreoffice() -> None:
    block = _backend_smoke_block()

    # A tracked fixture is converted by the image's soffice, so the input is a
    # genuine ODF document rather than a hand-written zip.
    assert "soffice --headless" in block
    assert "--convert-to odt" in block
    assert "test -s /smoke/out.md" in block
