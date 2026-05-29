# Design: mid MVP — CLI de conversión a Markdown

## Technical Approach

Greenfield CLI wrapping Microsoft MarkItDown. Four-layer architecture: **CLI** (argparse) → **Engine** (registry + orchestration) → **Converters** (ABC + impl) → **Models** (types + errors). Los converters nunca lanzan excepciones — usan `ConvertResult` con `success: bool`. Legacy placeholders en el mismo registry permiten agregar formatos sin tocar core.

## Architecture Decisions

| Decision | Options | Choice | Rationale |
|---|---|---|---|
| ConvertResult type | NamedTuple / dataclass | `@dataclass(frozen=True)` | Inmutable, typing explícito, sin overhead de hash |
| File discovery | `os.walk` / `Path.rglob` | `Path.rglob` | API moderna, Path objects, una expresión |
| Flatten collision | numbered / prefixed | `parent-stem.md` | Predecible, reversible, sin ambigüedad |
| Error propagation | exceptions / result obj | `ConvertResult.success` | Converters nunca lanzan; CLI traduce a exit codes |
| ABC location | base.py vs inline | `converters/base.py` | Un archivo por responsabilidad |
| PyInstaller mode | --onefile / --onedir | `--onefile` | Portable sin dependencias externas; migrar a --onedir si startup es lento |

## Data Flow

### `mid convert docs/reporte.docx -o out.md --json`

```
CLI: main() → parse_args()
 └─ handler_convert()
    ├─ engine.resolve_converter(".docx") → REGISTRY → MarkitDownConverter
    ├─ result = converter.convert(Path("docs/reporte.docx"))
    │    └─ MarkItDown API → str markdown
    ├─ CLI traduce result:
    │    ├─ --json → json.dumps(asdict(result)) → stdout
    │    ├─ -o     → Path.write_text(result.content)
    │    └─ stdout → print(result.content)
    └─ sys.exit(0 | 1 | 3)
```

### `mid batch ./in -o ./out --recursive --flatten`

```
CLI: handler_batch(args)
 ├─ discover: Path("./in").rglob("*")
 │    → filter: ext in REGISTRY → [a.docx, sub/b.docx, sub/sub2/c.pdf]
 ├─ for each:
 │    ├─ converter = resolve_converter(ext)
 │    ├─ result = converter.convert(path)
 │    ├─ out_rel = path.relative_to(input_dir)
 │    │    ├─ --flatten: out_rel = path.name (collision → "parent-{stem}.md")
 │    │    └─ --preserve: out_rel = path.with_suffix(".md")
 │    ├─ success? → write; else → stderr + failed++
 └─ print(f"Processed: N, Succeeded: S, Failed: F, Skipped: J")
    sys.exit(0)
```

### Registry resolution

`resolve_converter(ext)`: lower + dot → lookup → `REGISTRY[ext]`, `None`, o `LegacyPlaceholder`.

## File Changes

| File | Description |
|---|---|
| `pyproject.toml` | Metadata, setuptools, dependencias (markitdown) |
| `src/mid/__init__.py` | `__version__ = "0.1.0"` |
| `src/mid/__main__.py` | Entry point `python -m mid` → `cli.main()` |
| `src/mid/cli.py` | `setup_parser()` con subparsers `convert`, `batch`, `help`; handlers |
| `src/mid/engine.py` | `REGISTRY: Final[dict]`, `resolve_converter()`, `convert_file()` |
| `src/mid/exceptions.py` | `MidError` → `ConversionError`, `ArgumentError`, `UnsupportedFormatError` |
| `src/mid/models.py` | `ConvertResult` dataclass frozen |
| `src/mid/converters/__init__.py` | Re-exports |
| `src/mid/converters/base.py` | `class Converter(ABC)` con `supported_extensions` + `convert()` |
| `src/mid/converters/markitdown.py` | Wrapper sobre `markitdown.MarkItDown` |
| `src/mid/converters/legacy.py` | Siempre retorna error instructivo |
| `tests/test_converters.py` | Unit tests con mock MarkItDown |
| `tests/test_cli.py` | CLI via argparse mock |
| `tests/test_batch.py` | Batch: flatten, preserve, collision, non-fatal errors |
| `tests/fixtures/` | Documentos mínimos para tests E2E |
| `scripts/build.ps1` | PyInstaller → `dist/mid.exe` |
| `.gitignore` | Python + PyInstaller ignores |

## Interfaces / Contracts

```python
# models.py
@dataclass(frozen=True)
class ConvertResult:
    content: str
    metadata: dict          # {"source": str, "format": str, "success": bool}
    success: bool
    error: str | None

# converters/base.py
class Converter(ABC):
    supported_extensions: ClassVar[frozenset[str]]
    @abstractmethod
    def convert(self, path: Path) -> ConvertResult: ...

# engine.py — registro
REGISTRY: Final[dict[str, type[Converter]]] = {
    ".docx": MarkitDownConverter, ".xlsx": MarkitDownConverter,
    ".pptx": MarkitDownConverter, ".pdf":  MarkitDownConverter,
    ".doc":  LegacyPlaceholder,   ".xls":  LegacyPlaceholder,
    ".ppt":  LegacyPlaceholder,
}

def resolve_converter(ext: str) -> type[Converter] | None: ...
```

## Error Handling

| Condición | Exit | Mensaje |
|---|---|---|
| MarkItDown falla | 1 | `conversion failed: <msg>` |
| Missing FILE / not found | 2 | `argument FILE is required` / `file not found: <path>` |
| Ext no soportada | 3 | `unsupported format .<ext>` |
| Legacy (.doc) | 3 | `legacy format. Convert to .docx first` |

**Regla**: converters retornan `ConvertResult(success=False)`. Engine lanza `MidError`. CLI captura y traduce a `sys.exit(code)`.

## Batch Processing

- **Walk**: `Path(input).rglob("*")` si `--recursive`, sino `iterdir()`.
- **Output**: preserve → `rel_path.with_suffix(".md")`. Flatten → `path.name`; colisión → `parent-stem.md`.
- **Errores**: no fatales. Stats: `Processed: N, Succeeded: M, Failed: K, Skipped: J`.
- **Flatten sin recursive**: warning a stderr.

## Testing Strategy

| Capa | Scope | Enfoque |
|---|---|---|
| Unit | converters (mock MarkItDown), engine, models | Mock `markitdown.MarkItDown.convert` |
| Integration | CLI exit codes, `--json`, batch flatten/preserve | `sys.argv` mock + `tmp_path` fixtures |
| E2E | Real MarkItDown + .docx | `@pytest.mark.slow`, skip si no hay deps |

**Fixtures**: `tests/fixtures/gen_fixtures.py` genera .docx, .xlsx, .pptx, .pdf mínimos. **Coverage**: 85%+.

## Migration / Rollout

No migration required. MVP tag `v0.1.0` post-build.

## Resolved During Review

- ✅ MarkItDown version: `>=0.4.0` (flexible, minimum version)
- ✅ `--flatten` sin `--recursive`: error (exit code 2, mensaje: `--flatten requires --recursive`)
- ⏳ Hidden imports de PyInstaller: resolver empíricamente durante la fase de build (fase 5 del plan). Probar build, ejecutar, ver si falla, agregar --hidden-import según error.
