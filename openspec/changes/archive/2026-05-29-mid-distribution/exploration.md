## Exploration: mid distribution and release strategy

### Current State
`mid` is a setuptools-based Python CLI with a console entry point (`mid = mid.cli:main`), local `.venv` development workflow, and verified real `.docx` E2E conversion tests. The repo already has a Windows-focused PyInstaller build script (`scripts/build.ps1`) that emits `dist/mid.exe`, but there is no release pipeline, no installer bootstrap scripts, and no cross-platform distribution contract yet.

### Affected Areas
- `pyproject.toml` — package metadata, console script, and version source used by release artifacts.
- `scripts/build.ps1` — current Windows binary build baseline; likely template for CI packaging.
- `README.md` — install UX, update, and uninstall docs for users and terminal agents.
- `src/mid/__init__.py` — version pinning source (`__version__`) for release tagging consistency.
- `tests/test_cli.py`, `tests/test_batch.py` — smoke coverage entry points that should run against release candidates.
- `.github/workflows/*` (new) — CI/release automation for wheels + binaries + checksums.
- `openspec/changes/mid-distribution/exploration.md` — exploration artifact for this change.

### Approaches
1. **Python package only (`pipx` / `pip install`)** — Distribute via PyPI/GitHub Packages and install through Python tooling.
   - Pros: Lowest packaging complexity; native Python update/uninstall model; easy semver pinning.
   - Cons: Requires Python/runtime tooling on target host; less ergonomic for agent bootstrap; can be fragile across tool-managed environments.
   - Effort: Low

2. **Standalone binaries only (PyInstaller or Nuitka per OS)** — Publish OS-specific executables and install by download.
   - Pros: Best “just works” UX for agents; no Python prerequisite; deterministic runtime behavior.
   - Cons: Higher CI complexity (matrix builds + signing/checksums); larger artifacts; platform quirks (AV false positives, glibc compatibility).
   - Effort: Medium/High

3. **Hybrid distribution (package + standalone binaries)** — Publish both Python package and OS binaries, with bootstrap scripts defaulting to binaries.
   - Pros: Best compatibility and UX; binary-first for agents, package fallback for power users/devs; safer rollout path.
   - Cons: More moving parts than package-only; requires release discipline to keep artifacts in sync.
   - Effort: Medium

### Recommendation
Use a **hybrid, binary-first strategy** hosted on **GitHub Releases**.

Initial install UX:
- Windows: `irm https://<host>/install.ps1 | iex`
- Linux: `curl -fsSL https://<host>/install.sh | bash`

Installer behavior should be deterministic and non-interactive by default:
- Resolve version from `MID_VERSION` (if set) else latest GitHub release.
- Download `mid-<os>-<arch>` + `checksums.txt`; verify SHA-256 before install.
- Install user-local (no admin):
  - Windows: `%LOCALAPPDATA%\mid\bin\mid.exe`
  - Linux: `${MID_INSTALL_DIR:-$HOME/.local/bin}/mid`
- Add path entry if missing (user scope only).
- Support pinning and rollback by rerunning installer with `MID_VERSION=vX.Y.Z`.

Release hosting:
- GitHub Releases as canonical artifact channel (tag + notes + checksums + binaries + wheels/sdist).
- Keep package publishing as secondary channel (pipx/pip) for ecosystems where Python-based install is preferred.

Update/uninstall:
- Update: rerun installer (latest or pinned version).
- Uninstall: lightweight uninstall script per OS removes binary and managed path entry.
- Optional later phase: `mid self-update` / `mid self-uninstall` command wrappers.

Agent/tool consumption fit:
- Binary-first + user-local PATH is best for OpenCode/Claude Code-like terminal agents because it avoids Python env coupling, works in non-project shells, and keeps command resolution predictable.

### Risks
- Unsafely piping remote scripts can be blocked by org policy; mitigated with transparent script source + checksum verification + pinned version support.
- Linux binary compatibility can break across distros/glibc versions; mitigated by conservative build target and documented fallback to `pipx install mid`.
- Release drift (scripts referencing missing assets) can break installers; mitigated by release validation job before publish.

### Ready for Proposal
Yes — proceed with a scoped proposal for **Phase 1: GitHub Releases + Windows/Linux bootstrap installers + checksum verification + binary-first install docs**, while deferring advanced self-update features.
