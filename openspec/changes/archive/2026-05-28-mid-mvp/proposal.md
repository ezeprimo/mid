# Propuesta: mid MVP — CLI de conversión a Markdown

## Intent

CLI portable (`mid.exe`) que convierte documentos modernos (.docx, .xlsx, .pptx, .pdf) a Markdown usando Microsoft MarkItDown. Elimina fricción en flujos batch, pipelines CI y consumo por agentes de IA.

## Scope

### In Scope
- CLI `mid` con comandos `convert`, `batch`, `help`, flags `--json`, `--version`, `--list-formats`, `--help`
- Conversión single-file y batch con `--recursive`, `--flatten`/`--preserve`
- Output Markdown texto + JSON machine-readable
- Arquitectura extensible con ABC Converter + Registry
- Build PyInstaller → `dist/mid.exe` (Windows)

### Out of Scope
- Formatos legacy (.doc, .xls, .ppt) — placeholder con error instructivo
- Conversión inversa (Markdown → DOCX)
- API/servidor HTTP
- Linux/Mac builds

## CLI (interfaz completa)

```
mid --help / -h                      → ayuda general
mid convert --help                   → ayuda del subcomando convert
mid batch --help                     → ayuda del subcomando batch
mid help                             → ayuda general
mid help convert                     → ayuda del subcomando convert

mid convert report.docx              → stdout
mid convert report.docx -o out.md    → archivo
mid convert report.docx --json       → JSON stdout
mid -V / --version                   → "mid 0.1.0"
mid --list-formats                   → .docx .xlsx .pptx .pdf .doc .xls .ppt
mid batch ./docs -o ./out            → directorio a directorio
mid batch ./docs -o ./out --recursive
mid batch ./docs -o ./out --flatten  → plano
mid batch ./docs -o ./out --preserve → mantiene árbol
```

## Capabilities

### New
- `cli-interface`: argparse, errores consistentes, exit codes
- `document-conversion`: MarkItDown wrapper para 4 formatos
- `batch-conversion`: árbol de directorios, flatten/preserve
- `converter-architecture`: ABC, registry de extensiones
- `build-packaging`: PyInstaller vía `scripts/build.ps1`

## Approach

### Data Flow
```
mid convert doc.docx
 ├─ cli.py → argparse
 ├─ engine.py → registry[.docx] → MarkitDownConverter
 ├─ converter.py → MarkItDown API → str MD
 └─ cli.py → stdout | -o | --json
```

### Converter ABC
```python
class ConvertResult(NamedTuple):
    content: str
    metadata: dict
    success: bool
    error: str | None

class Converter(ABC):
    supported_extensions: ClassVar[frozenset[str]]
    @abstractmethod
    def convert(self, path: Path) -> ConvertResult: ...
```

### Registry
```python
REGISTRY: dict[str, Type[Converter]] = {
    ".docx": MarkitDownConverter, ".xlsx": MarkitDownConverter,
    ".pptx": MarkitDownConverter, ".pdf":  MarkitDownConverter,
    ".doc":  LegacyPlaceholder,   ".xls":  LegacyPlaceholder,
    ".ppt":  LegacyPlaceholder,
}
```

## Implementation Plan

| Fase | Qué incluye |
|------|-------------|
| 1. Scaffold | pyproject.toml, .gitignore, `__init__.py`, `__main__.py`, exceptions |
| 2. Core | base.py (ABC), engine.py (registry), cli.py (argparse) |
| 3. Converters | markitdown_converter.py, legacy_placeholder.py |
| 4. Batch | lógica batch en cli.py |
| 5. Build | scripts/build.ps1 + test PyInstaller |
| 6. Tests | unit tests converters + CLI, fixtures/ |

## Affected Areas

| Área | Cambio | Descripción |
|------|--------|-------------|
| `src/mid/` | New | Package raíz, CLI, engine, exceptions |
| `src/mid/converters/` | New | ABC, impl MarkItDown, legacy placeholder |
| `tests/` | New | Estructura + fixtures |
| `scripts/build.ps1` | New | Build PyInstaller |
| `pyproject.toml` | New | Metadata + dependencias |

## Risks

| Riesgo | Prob. | Mitigación |
|--------|-------|------------|
| MarkItDown falla en PDFs complejos | Med | Tests con variedad de PDFs; error claro al usuario |
| PyInstaller no empaqueta markitdown | Baja | Test build temprano, spec file manual si necesario |
| Documentos sin texto (solo imágenes) | Alta | Documentar: MarkItDown extrae texto, no OCR |

## Rollback

`git reset --hard HEAD` + borrar `openspec/changes/mid-mvp/`. Primer commit post-propuesta es punto de restauración.

## Success Criteria

- [ ] `mid convert sample.docx` escribe Markdown a stdout
- [ ] `mid batch . -o out --recursive` procesa árbol completo
- [ ] `mid --json` emite JSON parseable por agentes de IA
- [ ] `mid convert legacy.doc` muestra error instructivo con solución
- [ ] `scripts/build.ps1` genera `dist/mid.exe` funcional (convierte un .docx real)
