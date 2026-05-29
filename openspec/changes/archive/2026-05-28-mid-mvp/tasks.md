# Tasks: mid MVP — CLI de conversión a Markdown

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~700–800 (greenfield, 17 files) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: Scaffold + Core → PR 2: Converters + Batch → PR 3: Build + Tests |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Foundation + Core architecture | PR 1 | pyproject.toml, exceptions, models, ABC, engine, CLI skeleton. Base → main. |
| 2 | Converters + Batch logic | PR 2 | MarkItDown wrapper, legacy placeholder, batch, flatten, preserve, collision. Depends on PR 1. |
| 3 | Build + Tests | PR 3 | build.ps1, PyInstaller, unit/integration/batch tests, fixtures. Depends on PR 2. |

## Phase 1: Scaffold — Foundation

- [x] 1.1 `pyproject.toml` — metadata, markitdown>=0.1.0 (`>=0.4.0` no existe en PyPI), `[project.scripts] mid=mid.cli:main`
- [x] 1.2 `.gitignore` — Python + PyInstaller ignores
- [x] 1.3 `src/mid/__init__.py` — `__version__ = "0.1.0"`
- [x] 1.4 `src/mid/__main__.py` — `from .cli import main; main()`
- [x] 1.5 `src/mid/exceptions.py` — `MidError` → `ConversionError`, `ArgumentError`, `UnsupportedFormatError`
- [x] 1.6 `src/mid/models.py` — `ConvertResult` dataclass frozen

## Phase 2: Core — Engine + CLI Skeleton

- [x] 2.1 `converters/__init__.py` — re-exports: Converter, MarkitDownConverter, LegacyPlaceholder
- [x] 2.2 `converters/base.py` — `Converter(ABC)` with `supported_extensions` + `convert()`
- [x] 2.3 `engine.py` — `REGISTRY` (7 ext → 2 clases), `resolve_converter()`, `convert_file()`
- [x] 2.4 `cli.py` — `setup_parser()` con subparsers, `main()` traduce ConvertResult a exit codes

## Phase 3: Converters — Impl

- [x] 3.1 `converters/legacy.py` — `LegacyPlaceholder`: .doc/.xls/.ppt, convert() retorna error instructivo
- [x] 3.2 `converters/markitdown.py` — `MarkitDownConverter`: wrappea MarkItDown, captura excepciones → `ConvertResult(success=False)`

## Phase 4: Batch — Multi-file Processing

- [x] 4.1 `cli.py` — `handler_batch`: descubre archivos (rglob/iterdir), filtra por REGISTRY, itera con error continuation
- [x] 4.2 `cli.py` — output paths: `--preserve` replica árbol, `--flatten` → plano (collision `parent-stem.md`), `--flatten` sin `--recursive` → exit 2
- [x] 4.3 `cli.py` — summary report con `Processed/Succeeded/Failed/Skipped`, exit 0

## Phase 5: Build — PyInstaller

- [x] 5.1 `scripts/build.ps1` — `pyinstaller --onefile --name mid`, flags `--clean`, reporta exit code. Excluye packages pesados de conda (torch, tensorflow, etc.) que no necesita mid.
- [x] 5.2 Hidden imports empíricos: build → ejecutar `mid.exe convert` → funciona. Solo necesitó `--hidden-import markitdown`.

## Phase 6: Tests — Cobertura

- [x] 6.1 `tests/conftest.py` — fixtures pytest: sample_dir, nested_dir, collision_dir, mock_convert_success/failure
- [x] 6.2 `tests/test_converters.py` — mock MarkItDown, success/error, LegacyPlaceholder (15 tests)
- [x] 6.3 `tests/test_cli.py` — mock sys.argv + tmp_path, exit codes, --version, --list-formats, --json (14 tests)
- [x] 6.4 `tests/test_batch.py` — batch básico, recursive preserve/flatten, collision, error no fatal, --flatten sin --recursive (14 tests)
