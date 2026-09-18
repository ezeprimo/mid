# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Office backend OOXML intermediate**: `.doc`/`.xls` now save via COM as macro-free `.docx` (`wdFormatXMLDocument`, 12) / `.xlsx` (`xlOpenXMLWorkbook`, 51) and delegate to MarkItDown's native docx/xlsx reader instead of the HTML intermediate. HTML-only helpers (`_decode_html_bytes`, `_resolve_frameset_sheets`, `_clean_word_html`, meta-charset normalize) removed; 20 MB cap now applies to the OOXML intermediate. Multi-sheet workbooks convert whole (one `## <name>` section per sheet, no join step needed)

### Fixed

- **Office backend merged-cell forward-fill**: on the `.xls` path each merged range's top-left value is repeated into every cell (horizontal + vertical) before MarkItDown, so markdown rows are self-contained for AI readers instead of `||` gaps; only real merged ranges fill (spacer rows stay empty), normalization still runs after, never raises
- **Office backend OOXML markdown normalization**: final markdown maps literal U+00A0 → space (runs collapsed, `\n` kept), whole-cell `NaN` → empty cell (substrings like `financiero` kept), exact `Unnamed: N` headers → empty cell with column count stable; never raises, `.doc` output unchanged
- **Office backend Word HTML sanitizing (#32)**: strip `[if ...]` conditional blocks (list-number field codes leaked into headings) with inner content and normalize NBSP entities/literals to regular spaces before MarkItDown

### Added

- **Legacy backend framework (#12)**: shared `Backend` ABC + registry + local tool detection (2s cached never-raise probe) with `BackendAdapter` and engine/CLI seams; explicit selection via `mid convert --backend <name>` and `mid --list-backends`; exit `2` unknown backend, `3` unavailable backend
- **LibreOffice backend for local legacy conversion (#13)**: headless `soffice` backend (`--convert-to "html:XHTML Writer File:UTF8"`, isolated temp dirs, 20 MB output cap, strict UTF-8) delegating the HTML intermediate to MarkItDown; `MID_LIBREOFFICE_PATH` / `MID_LIBREOFFICE_TIMEOUT` (default 30s, 5..300); converts `.doc` (representative; `.xls`/`.ppt` via same backend)
- **Docker legacy image with LibreOffice (#14)**: `docker/Dockerfile.legacy` (Debian bookworm-slim, pinned LibreOffice 7.4.7 writer+calc+impress, non-root `USER mid`, ~1 GB, `linux/amd64`) with documented mount conversion, host-dir permission notes, and `docker-legacy.yml` CI (build + `.doc→.md` smoke, GHA cache, no registry push)
- **Office backend (Windows-only, opt-in)**: `office` backend converting legacy `.doc`/`.xls` via installed Word/Excel COM automation (`DispatchEx`, never attaches to a running instance). Registered only on `win32`, explicit `--backend office` required, `pywin32` behind the `office-windows` extra, `MID_OFFICE_PATH`/`MID_OFFICE_TIMEOUT` configuration, PID-scoped orphan cleanup, exit `2`/`3` mapping, `docs/office-backend.md`, explicit `--backend` selection now probes opt-in backends (`is_available(refresh=True)` in CLI/engine)

### Fixed

- **Office backend Word compat (#28)**: dropped the `WithWindow` keyword from `Documents.Open` (no such parameter — Word 2013 rejected it); hidden mode stays enforced via `Visible = False`
- **Office backend Excel encoding + orphans (#29)**: intermediate HTML now decodes with precedence declared meta charset → UTF-8 → windows-1252 and is normalized back to UTF-8; COM app wrapper is popped from the holder right after the worker joins with `gc.collect()` in `finally`, so no `EXCEL.EXE`/`WINWORD.EXE` stays alive nondeterministically
- **Office backend env-dependent test (#30)**: exit-2/exit-3 CLI mapping now covered by an env-independent stub test; the real-backend assertions skip (or assert gate-pass) based on the live `probe()` instead of assuming Office is absent
- **Office backend Excel frameset (follow-up of #29)**: `xlHtml` containers now resolve the referenced sheet files from the companion directory (locale-independent, tabstrip excluded, directory-contained) and convert their combined content instead of the frameset placeholder
- **Office backend lock taxonomy (follow-up of #29)**: numeric WinError 32/33/5 map to `file locked`/`permission denied` locale-independently (Spanish messages included); pre-COM copy failures route through `_map_error`

## [0.2.0] — 2026-08-31

### Added

- **Update checker banner**: TTY stderr banner when newer GitHub Release exists, 24h throttle (CACHE_TTL=86400), cache at platformdirs.user_cache_dir("mid")/update_cache.json fallback ~/.config/mid/.update_cache.json, perms 0700/0600, guards isatty/CI/GITHUB_ACTIONS/TERM=dumb/--help/--version/--json/--list-formats/MID_NO_UPDATE_CHECK, trunk allowlist, lazy httpx→urllib 2s timeout, rich optional, Windows irm variant, hook in cli.py:main() finally preserving exit codes 0-3
- **Uninstall cache cleanup**: uninstall.sh and uninstall.ps1 now remove update checker cache (6 candidates with XDG overrides, dedupe, --dry-run/-DryRun, empty parent rmdir) — respects XDG_CACHE_HOME/XDG_CONFIG_HOME
- **Agent verification workflow**: skills/mid-cli/SKILL.md new Decision Gate, Execution Step 7, and For Agents — Verifying New Versions (when/how, fetch_latest_version/is_newer, gh api/curl fallback, opt-out, cache 24h)
- **Dependencies**: platformdirs>=3.0, packaging>=24.0, httpx>=0.27, optional rich>=13.0

### Fixed

- Ruff lint fixes for update checker tests (F401/F841) and ruff format

### Tests

- **tests/test_update_checker.py**: 44 tests covering cache, semver, guards, banner stderr, throttle
- **tests/release/test_uninstall_bootstrap_contract.py**: +7 contract tests for cache cleanup dry-run/force/XDG/keep.txt (Linux bash + Windows pwsh)

## [0.1.1] — 2026-06-05

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

[Unreleased]: https://github.com/ezeprimo/mid/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/ezeprimo/mid/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ezeprimo/mid/releases/tag/v0.1.0
