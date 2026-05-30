# Tasks: Mid Distribution

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 860 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | ask-always |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Lock release contract + validation baseline | PR 1 | Version wiring, validator, release contract tests; if feature-chain, base = feature/tracker |
| 2 | Build and publish automation | PR 2 | Workflow + checksums + notes; if feature-chain, base = PR 1 branch |
| 3 | Bootstrap installers + docs/update/uninstall | PR 3 | install.ps1/install.sh + PATH/fallback docs; if feature-chain, base = PR 2 branch |

## Phase 1: Foundation / Release Contract

- [x] 1.1 Modify `src/mid/__init__.py` to keep canonical `__version__` aligned with release tags.
- [x] 1.2 Modify `pyproject.toml` to read version dynamically from `src/mid/__init__.py`.
- [x] 1.3 Create `scripts/release/validate_release.py` to enforce asset names, tag/version match, checksum entries, and required notes sections.
- [x] 1.4 RED: Create failing contract tests in `tests/release/test_release_contract.py` for stable assets, latest-vs-prerelease, and missing Linux checksum.
- [x] 1.5 GREEN: Implement validator logic so `tests/release/test_release_contract.py` passes against fixture release JSON.

## Phase 2: Build / Publish Automation

- [x] 2.1 Modify `scripts/build.ps1` to output `mid-windows-amd64.exe` and accept CI version/output parameters.
- [x] 2.2 Create `scripts/build.sh` to build Linux `mid-linux-amd64` with parity to Windows build behavior.
- [x] 2.3 Create `scripts/release/render_release_notes.py` with required install, pin, fallback, rollback, and uninstall sections.
- [x] 2.4 Create `.github/workflows/release.yml` to run matrix builds, build wheel/sdist, generate `checksums.txt`, run validator, and publish release on `vX.Y.Z`.
- [x] 2.5 Add workflow smoke checks in `.github/workflows/release.yml`: run built binary `--version` and one real `.docx` conversion before publish.

## Phase 3: Bootstrap Installers / Integration

- [x] 3.1 Create `install.ps1` to resolve `MID_VERSION` (pinned or latest stable), fetch release assets, verify SHA-256, and install atomically to `%LOCALAPPDATA%\mid\bin\mid.exe`.
- [x] 3.2 Add Windows PATH behavior in `install.ps1`: update user PATH when possible; otherwise print exact PATH entry and “new shell required” guidance.
- [x] 3.3 Create `install.sh` to resolve version via Releases API, install to `${MID_INSTALL_DIR:-$HOME/.local/bin}/mid`, and verify checksum before replace.
- [x] 3.4 Add Linux PATH stanza management in `install.sh` (`~/.profile`) plus explicit manual guidance when profile/PATH is not writable.
- [x] 3.5 Add version-aware `pipx`/`pip` fallback and phase-1 update/rollback/uninstall messaging in both installer scripts.

## Phase 4: Verification / Documentation

- [x] 4.1 Create `tests/release/test_install_bootstrap_contract.py` to validate resolver determinism, integrity-failure fallback output, and PATH failure guidance scenarios.
- [x] 4.2 Modify `README.md` with Windows/Linux install commands, `MID_VERSION` pinning, fallback guidance, update/rollback flow, and phase-1 uninstall steps.
- [x] 4.3 REFACTOR: Trim duplicated install/help text across `README.md` and `scripts/release/render_release_notes.py` while preserving required release-note sections.
