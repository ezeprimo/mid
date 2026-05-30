# Proposal: Mid Distribution

## Intent

Define a release strategy that makes `mid` easy to install and update for terminal-agent workflows, starting with Windows and Linux, without requiring users to manage Python first.

## Scope

### In Scope
- GitHub Releases as the canonical source for tagged binaries, wheels/sdist, release notes, and `checksums.txt`.
- Binary-first install UX with `install.ps1` and `install.sh`, user-local install paths, version pinning, and checksum verification.
- Phase-1 release/docs workflow covering asset naming, publish/validation automation, and documented `pipx`/`pip` fallback.

### Out of Scope
- macOS distribution, package managers, and code signing/notarization.
- `mid self-update` / `mid self-uninstall` commands beyond script-based update/uninstall.

## Capabilities

### New Capabilities
- `release-distribution`: Define how `mid` publishes versioned binaries and Python packages through GitHub Releases with verifiable assets.
- `install-bootstrap`: Define non-interactive Windows/Linux bootstrap installation, upgrade, rollback, and uninstall behavior for local CLI setup.

### Modified Capabilities
- None.

## Approach

Adopt the exploration recommendation: hybrid distribution, binary-first UX, GitHub Releases as canonical host, and `pipx`/`pip` as fallback. Ship Windows first but require Linux assets in the initial contract so installer behavior, docs, and release validation stay aligned from day one.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `.github/workflows/` | New | Release/build/validation workflow for binaries, packages, and checksums |
| `scripts/` | Modified/New | Bootstrap installers and release helper scripts |
| `README.md` | Modified | Install, upgrade, rollback, uninstall, and fallback docs |
| `pyproject.toml` | Modified | Package/release metadata alignment |
| `src/mid/__init__.py` | Modified | Version source consistency for tagging |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Linux binary incompatibility | Med | Conservative target + documented `pipx` fallback |
| Release asset drift | Med | Validation before publish |
| Remote-script trust concerns | High | Transparent scripts + SHA-256 verification + version pinning |

## Rollback Plan

Disable installer docs/scripts, stop publishing bootstrap entrypoints, and direct users to the last known-good GitHub Release or `pipx` install path while fixing release automation.

## Dependencies

- GitHub Releases and Actions availability
- Existing Windows build baseline in `scripts/build.ps1`

## Success Criteria

- [ ] A reviewer can identify the Phase-1 release artifacts, install surfaces, and fallback channel without design-level guesswork.
- [ ] The change is scoped to a reviewable first rollout: Windows + Linux installers, checksums, release assets, and supporting docs/workflow.
