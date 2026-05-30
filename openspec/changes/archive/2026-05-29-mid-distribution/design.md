# Design: Mid Distribution

## Technical Approach

Phase 1 uses GitHub Releases as the only distribution contract. A tag `vX.Y.Z` triggers one release workflow that builds installer-consumed binaries for Windows/Linux, builds wheel + sdist, validates names/version/checksums/runtime, generates release notes, and then publishes one release. Root `install.ps1` and `install.sh` stay stable entrypoints; they resolve `MID_VERSION` exactly or latest stable via the GitHub Releases API, verify SHA-256, smoke-run the downloaded binary, install user-local, and fall back to `pipx`/`pip` with the resolved version when binary install is unsafe.

| Asset | Phase 1 |
|---|---|
| Windows binary | `mid-windows-amd64.exe` |
| Linux binary | `mid-linux-amd64` |
| Wheel | `mid-{version}-py3-none-any.whl` |
| sdist | `mid-{version}.tar.gz` |
| Integrity | `checksums.txt` with binary SHA-256 entries |
| Manual archives | Deferred; reserved names `mid-windows-amd64.zip`, `mid-linux-amd64.tar.gz` |

## Architecture Decisions

| Topic | Options | Decision / rationale |
|---|---|---|
| Version source | duplicate literals vs single source | Make `pyproject.toml` read version dynamically from `src/mid/__init__.py`; release validation also checks tag `vX.Y.Z` == package version to stop drift. |
| Release publish | manual release vs gated workflow | Add `.github/workflows/release.yml` with build, validate, and publish jobs so the contract is enforced before assets become public. |
| Asset lookup | construct URLs only vs release API | Use `releases/latest` for latest stable and `releases/tags/{tag}` for pinned installs, then select exact asset names from JSON. This avoids prerelease leakage and asset-name drift. |
| Installer payload | archive-first vs raw binary-first | Installers consume raw binaries named by contract; archives are optional later. This matches the spec and keeps phase 1 small. |
| PATH mutation | admin/global vs user-only | Windows updates user PATH; Linux writes/removes a managed stanza in `~/.profile` when needed. If not writable, scripts print the exact entry and never claim immediate availability. |

## Data Flow

```text
tag vX.Y.Z
  -> .github/workflows/release.yml
     -> build-windows / build-linux / build-python
     -> scripts/release/validate_release.py
     -> scripts/release/render_release_notes.py + checksums.txt
     -> GitHub Release

install.ps1 / install.sh
  -> resolve release JSON
  -> download binary + checksums.txt
  -> verify SHA-256
  -> run `mid --version`
  -> atomic replace in user bin
  -> ensure PATH or print next steps
  -> emit version-aware pipx/pip fallback on unsupported or invalid binaries
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `.github/workflows/release.yml` | Create | Tag-driven matrix build, validation, checksum generation, notes generation, and release publish. |
| `install.ps1` | Create | Windows bootstrap for latest/pinned install, update, and rollback. |
| `install.sh` | Create | Linux bootstrap for latest/pinned install, update, and rollback. |
| `scripts/build.ps1` | Modify | Parameterize CI output/version and reuse existing Windows PyInstaller baseline. |
| `scripts/build.sh` | Create | Linux PyInstaller build baseline matching Windows behavior. |
| `scripts/release/validate_release.py` | Create | Enforce asset names, checksum manifest, tag/version match, and required notes sections. |
| `scripts/release/render_release_notes.py` | Create | Generate install, pin, fallback, rollback, and uninstall sections for release notes. |
| `pyproject.toml` | Modify | Dynamic version wiring and Python package build config. |
| `src/mid/__init__.py` | Modify | Canonical package version source. |
| `README.md` | Modify | Binary-first install, fallback, update, rollback, and uninstall documentation. |
| `tests/release/test_release_contract.py` | Create | Contract tests for asset selection, checksums, and release-note requirements. |

## Interfaces / Contracts

```text
Env:
MID_VERSION=vX.Y.Z
MID_INSTALL_DIR=/custom/bin   # Linux override

checksums.txt:
<sha256>  mid-windows-amd64.exe
<sha256>  mid-linux-amd64
```

- Windows target: `%LOCALAPPDATA%\mid\bin\mid.exe`
- Linux target: `${MID_INSTALL_DIR:-$HOME/.local/bin}/mid`
- Update/rollback: rerun installer with latest or pinned `MID_VERSION`
- Uninstall (phase 1): documented removal of installed binary plus managed PATH entry; no `mid self-update` or `mid self-uninstall` yet

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | asset naming, checksum parsing, note sections, version resolver helpers | `pytest` under `tests/release/` |
| Integration | helper scripts against fixture release JSON and assembled artifact directories | Python tests in local `.venv` and CI |
| E2E | release workflow before publish | run existing pytest suite, then run built binaries on Windows/Linux for `--version` and a real `.docx` conversion before release |

## Migration / Rollout

No data migration. Roll out in one reviewable slice: version-source cleanup, workflow/helpers, installer scripts, and docs. First validate on a prerelease tag, then enable stable tags for publish. Update is installer rerun; rollback is pinned reinstall; uninstall is documented manual cleanup in phase 1.

## Open Questions

- [ ] None blocking; Linux binary compatibility remains an operational risk and is mitigated by conservative CI target plus `pipx`/`pip` fallback.
