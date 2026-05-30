# release-distribution Specification

## Purpose

Define the GitHub Releases contract for `mid` artifacts, versions, integrity, and minimum release documentation.

## Requirements

### Requirement: Release Artifact and Naming Contract

For each tag `vX.Y.Z`, the system MUST publish Windows binary, Linux binary, wheel, sdist, `checksums.txt`, and release notes. Binary names MUST follow `mid-{os}-{arch}` (`.exe` on Windows, no extension on Linux).

#### Scenario: Stable release has complete, contract-compliant assets

- GIVEN tag `v1.2.3` is published
- WHEN a reviewer inspects Release `v1.2.3`
- THEN the required assets exist with contract-compliant names
- AND wheel/sdist versions match `1.2.3`

### Requirement: Version Resolution Contract

The system MUST support pinning with `vX.Y.Z`. `latest` MUST resolve to the newest stable release. Prereleases MUST NOT be selected unless pinned.

#### Scenario: Latest and pinned resolution are deterministic

- GIVEN stable `v1.2.3` and prerelease `v1.3.0-rc1` exist
- WHEN a bootstrap flow requests `latest`
- THEN `v1.2.3` is selected
- AND WHEN `v1.2.3` is pinned, that exact version is selected

### Requirement: Release Integrity Manifest

The system MUST publish `checksums.txt` with SHA-256 entries for installer-consumed binaries. Validation MUST fail when required entries are missing or malformed.

#### Scenario: Invalid checksum manifest blocks release compliance

- GIVEN a release is missing the Linux checksum entry
- WHEN release validation runs
- THEN validation reports non-compliance
- AND the release is not considered installable by contract

### Requirement: Minimum Release Documentation

Release notes MUST include Windows and Linux install commands, a version-pinning example, fallback (`pipx`/`pip`) instructions, and rollback guidance via pinned reinstall.

#### Scenario: Release notes include required operator instructions

- GIVEN release notes for `v1.2.3`
- WHEN a reviewer checks mandatory sections
- THEN all required install, fallback, and rollback instructions are present
