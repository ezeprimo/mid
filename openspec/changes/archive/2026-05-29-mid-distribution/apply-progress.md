# Apply Progress: mid-distribution

## Slice

- Work unit: PR 4 phase-4 verification/docs close-out (feature-branch-chain)
- Mode: Standard (strict_tdd not active)
- Hardening slice: close explicit verify-report runtime gaps for bootstrap + packaging proof

## Completed Tasks

- [x] 1.1 Canonical `__version__` maintained in `src/mid/__init__.py`
- [x] 1.2 `pyproject.toml` now reads version dynamically from `mid.__version__`
- [x] 1.3 Added `scripts/release/validate_release.py`
- [x] 1.4 Added release contract tests in `tests/release/test_release_contract.py`
- [x] 1.5 Implemented validator logic so release contract tests pass
- [x] 2.1 Updated `scripts/build.ps1` for `mid-windows-amd64.exe` and CI `-Version`/`-OutputDir`
- [x] 2.2 Added `scripts/build.sh` to produce `mid-linux-amd64` with matching options
- [x] 2.3 Added `scripts/release/render_release_notes.py` for required release-note sections
- [x] 2.4 Added `.github/workflows/release.yml` with matrix builds, wheel/sdist, checksums, validator, and publish baseline
- [x] 2.5 Added release workflow smoke checks for `--version` and real `.docx` conversion
- [x] 3.1 Added `install.ps1` to resolve latest/pinned releases, verify SHA-256, and install atomically to `%LOCALAPPDATA%\mid\bin\mid.exe`
- [x] 3.2 Added Windows user PATH handling in `install.ps1` with exact manual fallback guidance and new-shell notice
- [x] 3.3 Added `install.sh` to resolve latest/pinned releases and install to `${MID_INSTALL_DIR:-$HOME/.local/bin}/mid`
- [x] 3.4 Added Linux `~/.profile` PATH stanza management with manual guidance if profile updates fail
- [x] 3.5 Added version-aware `pipx`/`pip` fallback plus update/rollback/uninstall messaging in both installers
- [x] 4.1 Added `tests/release/test_install_bootstrap_contract.py` for resolver determinism, integrity-fallback guidance, and PATH failure guidance contracts
- [x] 4.2 Updated `README.md` with Windows/Linux release install commands, `MID_VERSION` pinning, fallback, update/rollback, and phase-1 uninstall guidance
- [x] 4.3 Refactored `scripts/release/render_release_notes.py` to DRY operator-section rendering while preserving required sections
- [x] Hardening: Upgraded installer verification to executable runtime harness coverage for Windows install, Linux install, pinned rollback, integrity-failure guidance, and PATH-failure guidance
- [x] Hardening: Added installer test hooks (`MID_API_BASE`, `MID_RAW_BASE`, smoke-pattern override, optional persistent PATH-disable flags) and Linux parser override (`MID_PYTHON_BIN`) for hermetic/runtime tests without changing default user behavior
- [x] Hardening: Added local dev dependency path for packaging verification (`.[dev]` includes `build`) and re-ran wheel/sdist generation from repo `.venv`

## Verification

- `./.venv/Scripts/python -m pytest tests/release/test_release_contract.py -q` → 4 passed
- `./.venv/Scripts/python -m pytest tests/test_cli.py::TestVersion::test_long_flag -q` → 1 passed
- `./.venv/Scripts/python -m pytest tests/release/test_release_contract.py tests/release/test_render_release_notes.py -q` → 6 passed
- `./.venv/Scripts/python -m pytest tests/release/test_release_contract.py tests/release/test_render_release_notes.py tests/release/test_install_bootstrap_contract.py -q` → 9 passed
- `./.venv/Scripts/python scripts/release/render_release_notes.py --version v1.2.3 --repo ezeprimo/mid --output C:/Users/ezepr/AppData/Local/Temp/opencode/release-notes-smoke.md` → OK
- `./.venv/Scripts/python scripts/release/render_release_notes.py --version v1.2.3 --repo ezeprimo/mid --output C:/Users/ezepr/AppData/Local/Temp/opencode/mid-release-notes-phase4.md` → OK
- `bash -n install.sh` → OK
- `PowerShell parser check for install.ps1` → OK
- `./.venv/Scripts/python -m pytest tests/release/test_install_bootstrap_contract.py tests/release/test_release_contract.py tests/release/test_render_release_notes.py -q` → 10 passed
- `./.venv/Scripts/python -m build --sdist --wheel --outdir C:/Users/ezepr/AppData/Local/Temp/opencode/mid-verify-build` → OK (`mid-0.1.0.tar.gz`, `mid-0.1.0-py3-none-any.whl`)

## Notes

- Scope for this final slice stayed within Phase 4 close-out (bootstrap contract tests, release/install docs, and release-note text DRY refactor) without expanding into self-update, signing, package managers, or extra OS targets.
- Runtime Linux harness execution under Windows required normalizing CRLF-sensitive fixture output and handling bash-side tool differences (`python3` availability, path translation); these are now represented in executable tests instead of string checks only.
