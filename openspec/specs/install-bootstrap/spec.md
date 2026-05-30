# install-bootstrap Specification

## Purpose

Define non-interactive bootstrap install, update, rollback, and fallback behavior for Windows and Linux users of `mid`.

## Requirements

### Requirement: Windows Bootstrap Behavior

The system MUST support `irm <url>/install.ps1 | iex`. Bootstrap MUST install `mid.exe` to `%LOCALAPPDATA%\mid\bin\mid.exe` by default without admin privileges.

#### Scenario: Windows bootstrap installs to user-local path

- GIVEN a supported Windows host and a valid release
- WHEN the user runs the documented PowerShell install command
- THEN `mid.exe` is installed at `%LOCALAPPDATA%\mid\bin\mid.exe`
- AND install completes non-interactively

### Requirement: Linux Bootstrap Behavior

The system MUST support `curl -fsSL <url>/install.sh | bash`. Bootstrap MUST install `mid` to `${MID_INSTALL_DIR:-$HOME/.local/bin}/mid` without sudo.

#### Scenario: Linux bootstrap installs to user-local path

- GIVEN a supported Linux host and a valid release
- WHEN the user runs the documented shell install command
- THEN `mid` is installed at `${MID_INSTALL_DIR:-$HOME/.local/bin}/mid`
- AND install completes non-interactively

### Requirement: Version Pinning and Rollback Behavior

The system MUST honor `MID_VERSION=vX.Y.Z` as an exact install target. When unset, it MUST install latest stable. Re-running bootstrap with an older version MUST provide rollback.

#### Scenario: Pinned install and rollback are user-controllable

- GIVEN `v1.2.3` and `v1.2.2` exist
- WHEN the user runs bootstrap with `MID_VERSION=v1.2.3` then `MID_VERSION=v1.2.2`
- THEN the installed executable version changes accordingly

### Requirement: PATH and Command Availability

The system MUST ensure the install directory is in user-scope PATH. If PATH cannot be updated automatically, it MUST provide explicit next steps and MUST NOT claim immediate command availability.

#### Scenario: PATH update failure gives actionable guidance

- GIVEN installation succeeds but PATH update is blocked
- WHEN bootstrap finishes
- THEN output explains the exact PATH entry to add
- AND output states a new shell may be required

### Requirement: Integrity and Fallback Behavior

Before replacing binaries, bootstrap MUST verify binary checksum against release `checksums.txt`. On integrity or compatibility failure, bootstrap MUST provide fallback via `pipx` or `pip` with the same version target when possible.

#### Scenario: Integrity failure triggers safe fallback guidance

- GIVEN checksum validation fails for a downloaded binary
- WHEN bootstrap validates artifacts
- THEN installation is aborted for that binary
- AND output provides version-aware `pipx`/`pip` fallback instructions
