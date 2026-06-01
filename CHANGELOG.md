# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Repository LICENSE file (Apache 2.0)
- Publication metadata in pyproject.toml (authors, license)
- GitHub Actions CI workflow for push and pull_request
- CHANGELOG.md file

## [0.1.0] — 2026-05-29

### Added

- **Core CLI**: `mid convert`, `mid batch`, `mid help` subcommands with argparse
- **MarkItDown backend**: Real conversion for `.docx`, `.xlsx`, `.pptx`, `.pdf` via `markitdown[all]`
- **Legacy format handling**: `.doc`, `.xls`, `.ppt` detected and rejected with clear migration guidance (exit code 3)
- **JSON output mode**: `mid convert --json` emits structured content + metadata
- **Batch conversion**: `mid batch` with flat, recursive, `--preserve`, and `--flatten` modes; collision-safe output naming
- **Exit codes**: 0 (success), 1 (conversion error), 2 (argument error), 3 (unsupported format)
- **`--list-formats`** flag to enumerate all registered extensions
- **Abstract converter interface**: `Converter` ABC with `MarkitDownConverter` and `LegacyPlaceholder`
- **Engine registry**: Extension-to-converter mapping in `mid.engine.REGISTRY`
- **Docker packaging**: Multi-stage build producing a standalone `mid` binary on Debian slim
- **Agent skill**: Repo-distributed `mid-cli` skill with references and cross-platform installer helpers
- **Build automation**: Windows (`build.ps1`) and Linux (`build.sh`) PyInstaller scripts
- **Release workflow**: `.github/workflows/release.yml` — matrix binary builds, wheel/sdist, checksums, validation, and GitHub Release publishing
- **Bootstrap installers**: `install.ps1` (Windows) and `install.sh` (Linux) with version pin, checksum verification, PATH management, and pipx/pip fallback
- **Release validation**: `scripts/release/validate_release.py` and associated contract tests
- **Release notes rendering**: `scripts/release/render_release_notes.py`

[Unreleased]: https://github.com/ezeprimo/mid/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ezeprimo/mid/releases/tag/v0.1.0
