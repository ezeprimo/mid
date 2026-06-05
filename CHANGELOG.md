# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **MarkItDown output quality**: Suppress spurious ffmpeg/pydub RuntimeWarning during import via `warnings.catch_warnings()`
- **Excel merged cell headers**: Detect `Unnamed:` / `NaN` patterns in table header rows and promote the first data row as the new header with a generated separator
- **TOC literal text**: Strip numbered TOC entries (e.g. "1. Introduction 3") that leak as plain text before the first heading
- **Regression guard**: Added 18 unit tests for post-processing methods (`_clean_unnamed_headers`, `_strip_toc_text`, `_cleanup`, ffmpeg suppression)

### Added

- **Converter test suite**: 18 new tests across 4 test classes covering the new post-processing pipeline

## [0.1.0] — 2026-06-03

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
- **GitHub Actions CI**: Lint + test matrix across Python 3.10–3.12
- **CONTRIBUTING.md**: Contribution guidelines
- **License file**: Apache 2.0 `LICENSE`
- **Publication metadata**: `pyproject.toml` with authors, classifiers, and project URLs
- **Uninstall contract tests**: Python/pytest tests for `uninstall.sh` and `uninstall.ps1`

### Fixed

- **Critical bugs**: N+1 edge cases, batch `rglob` PermissionError guard, `relative_to` ValueError guard, PATH split against null in install.ps1 session PATH
- **Installer hardening**: Cross-platform edge cases, version pin validation, integrity checks
- **CI/CD hardening**: Workflow permissions, step isolation, error handling
- **Build scripts**: Edge cases, cleanup, packaging flag guard for runtime compatibility
- **10 coverage gaps**: Tests added for edge cases found in Judgment Day review
- **Pre-release blockers**: Metadata alignment with PEP 639, ruff formatting

### Changed

- **mid-cli skill**: Restructured from developer/packaging focus to external agent usage instructions
- **Project contact**: Set to `ezeprimo.ia@gmail.com` using GitHub noreply alias
- **Repository prepared for public visibility**

[Unreleased]: https://github.com/ezeprimo/mid/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ezeprimo/mid/releases/tag/v0.1.0
