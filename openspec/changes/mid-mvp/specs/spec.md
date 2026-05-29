# mid — Specification Consolidada (MVP)

## Propósito

CLI portable `mid` que convierte documentos (.docx, .xlsx, .pptx, .pdf) a Markdown usando Microsoft MarkItDown, con soporte batch, output machine-readable y arquitectura extensible.

---

## 1. cli-interface — Interfaz de línea de comandos

### Propósito

Parser de argumentos (argparse), comandos, flags, exit codes y mensajes de error consistentes.

### Requirements

| ID | Requirement | Fuerza |
|---|---|---|
| CLI-01 | El sistema DEBE exponer los comandos `convert`, `batch` y `help` | MUST |
| CLI-02 | El sistema DEBE parsear `mid --help` y `mid -h` mostrando ayuda general y lista de comandos | MUST |
| CLI-03 | El sistema DEBE parsear `mid convert --help` y `mid batch --help` mostrando ayuda del subcomando | MUST |
| CLI-04 | El sistema DEBE mostrar versión con `mid --version` o `mid -V` con formato `mid X.Y.Z` | MUST |
| CLI-05 | El sistema DEBE listar formatos soportados con `mid --list-formats` en una línea separada por espacios | MUST |
| CLI-06 | El sistema DEBE soportar `mid help` (ayuda general) y `mid help convert` / `mid help batch` como alias de `--help` | MUST |
| CLI-07 | El sistema DEBE retornar exit code `0` en éxito, `1` en error de conversión, `2` en error de argumentos, `3` en archivo no soportado | MUST |
| CLI-08 | El sistema DEBE emitir errores a stderr con formato `error: <mensaje>` | MUST |

#### Scenario: CLI-01 — Convert con flags básicos

- GIVEN el ejecutable `mid` instalado y un archivo `reporte.docx` existente
- WHEN se ejecuta `mid convert reporte.docx -o out.md --json`
- THEN el comando retorna exit code 0
- AND se escribe `out.md` con contenido Markdown
- AND se emite JSON a stdout con estructura `{"content": "...", "metadata": {...}}`

#### Scenario: CLI-01 — Convert sin output (stdout)

- GIVEN el ejecutable `mid` instalado y un archivo `doc.docx`
- WHEN se ejecuta `mid convert doc.docx`
- THEN el Markdown convertido se escribe a stdout
- AND el exit code es 0

#### Scenario: CLI-07 — Error de argumentos (archivo faltante)

- GIVEN el ejecutable `mid` instalado
- WHEN se ejecuta `mid convert` (sin argumento de archivo)
- THEN el sistema escribe `error: argument FILE is required` a stderr
- AND el exit code es 2

#### Scenario: CLI-07 — Error de archivo no soportado

- GIVEN el ejecutable `mid` instalado y un archivo `imagen.png`
- WHEN se ejecuta `mid convert imagen.png`
- THEN el sistema escribe `error: unsupported format .png` a stderr
- AND el exit code es 3

#### Scenario: CLI-04 — Version flag

- GIVEN el ejecutable `mid` instalado
- WHEN se ejecuta `mid --version`
- THEN stdout contiene `mid 0.1.0` (o versión del paquete)
- AND exit code es 0

#### Scenario: CLI-05 — List formats

- GIVEN el ejecutable `mid` instalado
- WHEN se ejecuta `mid --list-formats`
- THEN stdout contiene `.docx .xlsx .pptx .pdf .doc .xls .ppt`
- AND exit code es 0

---

## 2. document-conversion — Conversión de documentos (MarkItDown)

### Propósito

Wrapper sobre Microsoft MarkItDown que convierte archivos individuales .docx, .xlsx, .pptx y .pdf a Markdown.

### Requirements

| ID | Requirement | Fuerza |
|---|---|---|
| DOC-01 | El sistema DEBE convertir archivos `.docx` a Markdown válido | MUST |
| DOC-02 | El sistema DEBE convertir archivos `.xlsx` a Markdown (tablas representadas como tablas Markdown) | MUST |
| DOC-03 | El sistema DEBE convertir archivos `.pptx` a Markdown (diapositivas como encabezados + contenido) | MUST |
| DOC-04 | El sistema DEBE convertir archivos `.pdf` a Markdown (texto extraído secuencialmente) | MUST |
| DOC-05 | El sistema DEBE retornar error instructivo para `.doc`, `.xls`, `.ppt` indicando formato legacy y solución | MUST |
| DOC-06 | El sistema DEBE soportar flag `--json` que emite `{"content": "...", "metadata": {"source": "...", "format": "...", "success": true}, "error": null}` | MUST |
| DOC-07 | El sistema DEBE retornar exit code 1 si MarkItDown falla internamente | MUST |

#### Scenario: DOC-01 — Conversión .docx exitosa

- GIVEN un archivo `resumen.docx` con texto, imágenes y tablas
- WHEN se ejecuta `mid convert resumen.docx -o resumen.md`
- THEN `resumen.md` existe
- AND el contenido incluye el texto extraído
- AND tablas convertidas a sintaxis Markdown
- AND exit code es 0

#### Scenario: DOC-05 — Formato legacy con error instructivo

- GIVEN un archivo `antiguo.doc`
- WHEN se ejecuta `mid convert antiguo.doc`
- THEN stderr contiene `error: .doc is a legacy format. Convert to .docx first using Microsoft Word or LibreOffice`
- AND exit code es 3

#### Scenario: DOC-07 — Error interno MarkItDown

- GIVEN un archivo `corrupto.pdf` que MarkItDown no puede procesar
- WHEN se ejecuta `mid convert corrupto.pdf`
- THEN stderr contiene `error: conversion failed: <mensaje de MarkItDown>`
- AND exit code es 1

#### Scenario: DOC-06 — Output JSON parseable

- GIVEN un archivo `datos.xlsx` válido
- WHEN se ejecuta `mid convert datos.xlsx --json`
- THEN stdout es un JSON válido con `content`, `metadata` y sin `error`
- AND el JSON es parseable por `json.loads()` sin ambigüedad
- AND `metadata.format` es `xlsx`
- AND exit code es 0

#### Scenario: DOC-01 — Documento vacío (sin texto)

- GIVEN un archivo `vacio.docx` sin contenido textual
- WHEN se ejecuta `mid convert vacio.docx`
- THEN stdout contiene cadena Markdown vacía o mínima ("")
- AND exit code es 0
- NOTA: MarkItDown extrae texto, no realiza OCR

---

## 3. batch-conversion — Conversión batch

### Propósito

Procesar directorios completos aplicando el converter a cada archivo soportado, con control sobre estructura de salida.

### Requirements

| ID | Requirement | Fuerza |
|---|---|---|
| BATCH-01 | El sistema DEBE aceptar `mid batch <dir-input> -o <dir-output>` y convertir todos los archivos soportados en `<dir-input>` | MUST |
| BATCH-02 | El sistema DEBE soportar `--recursive` para procesar subdirectorios | MUST |
| BATCH-03 | El sistema DEBE soportar `--flatten` en modo recursivo: todos los outputs en un solo directorio plano | MUST |
| BATCH-04 | El sistema DEBE soportar `--preserve` en modo recursivo: replica la estructura de directorios | MUST |
| BATCH-05 | Sin `--recursive`, el sistema DEBE ignorar subdirectorios y solo procesar archivos en el nivel raíz | MUST |
| BATCH-06 | El sistema DEBE omitir archivos con extensiones no soportadas sin generar error | MUST |
| BATCH-07 | El batch DEBE continuar si un archivo individual falla (error no fatal) y reportar el total al final | MUST |
| BATCH-08 | El sistema DEBE mostrar resumen al final: `Processed: N, Succeeded: M, Failed: K, Skipped: J` | MUST |
| BATCH-09 | Flag `--flatten` SIN `--recursive` DEBE ser ignorado con advertencia | SHOULD |

#### Scenario: BATCH-01 — Batch básico directorio plano

- GIVEN el directorio `entrada/` con `a.docx`, `b.pdf` y `notas.txt`
- WHEN se ejecuta `mid batch entrada -o salida`
- THEN `salida/a.md` y `salida/b.md` existen
- AND `salida/notas.md` NO existe (.txt no soportado)
- AND exit code es 0
- AND stdout contiene resumen: `Processed: 2, Succeeded: 2, Failed: 0, Skipped: 1`

#### Scenario: BATCH-02/04 — Batch recursivo preserve

- GIVEN `entrada/` con `sub/a.docx` y `sub/sub2/b.pdf`
- WHEN se ejecuta `mid batch entrada -o salida --recursive --preserve`
- THEN `salida/sub/a.md` y `salida/sub/sub2/b.md` existen (misma estructura)
- AND exit code es 0

#### Scenario: BATCH-03 — Batch recursivo flatten

- GIVEN `entrada/` con `sub/a.docx` y `sub/sub2/b.pdf`
- WHEN se ejecuta `mid batch entrada -o salida --recursive --flatten`
- THEN `salida/a.md` y `salida/b.md` existen (plano, sin subdirectorios)
- AND exit code es 0

#### Scenario: BATCH-07 — Error no fatal en batch

- GIVEN `entrada/` con `ok.docx` y `corrupto.pdf` (corrupto)
- WHEN se ejecuta `mid batch entrada -o salida`
- THEN `salida/ok.md` existe
- AND `salida/corrupto.md` NO existe
- AND stdout contiene resumen con `Succeeded: 1, Failed: 1`
- AND exit code es 0 (batch completo, fallos no fatales)

#### Scenario: BATCH-06 — Archivos no soportados ignorados

- GIVEN `entrada/` con `a.docx`, `imagen.png`, `data.csv`
- WHEN se ejecuta `mid batch entrada -o salida`
- THEN solo `salida/a.md` existe
- AND resumen muestra `Skipped: 2`

#### Scenario: BATCH-02 — Sin --recursive ignora subdirectorios

- GIVEN `entrada/` con `a.docx` y `sub/b.docx`
- WHEN se ejecuta `mid batch entrada -o salida`
- THEN `salida/a.md` existe
- AND `salida/sub/b.md` NO existe
- AND resumen muestra `Processed: 1`

---

## 4. converter-architecture — Arquitectura de converters

### Propósito

ABC (Abstract Base Class) para converters, Registry de extensiones y modelo ConvertResult, permitiendo agregar nuevos formatos sin modificar el core.

### Requirements

| ID | Requirement | Fuerza |
|---|---|---|
| ARCH-01 | El sistema DEBE definir un ABC `Converter` con método abstracto `convert(path: Path) -> ConvertResult` | MUST |
| ARCH-02 | El sistema DEBE definir `ConvertResult` como NamedTuple con campos `content: str`, `metadata: dict`, `success: bool`, `error: str | None` | MUST |
| ARCH-03 | El sistema DEBE exponer un `REGISTRY: dict[str, Type[Converter]]` que mapee extensión a clase converter | MUST |
| ARCH-04 | El `REGISTRY` DEBE contener entradas para `.docx`, `.xlsx`, `.pptx`, `.pdf`, `.doc`, `.xls`, `.ppt` | MUST |
| ARCH-05 | El sistema DEBE usar `LegacyPlaceholder` (que retorna error instructivo) para `.doc`, `.xls`, `.ppt` | MUST |
| ARCH-06 | Cada converter DEBE declarar `supported_extensions: ClassVar[frozenset[str]]` con las extensiones que maneja | MUST |

#### Scenario: ARCH-01/02 — ConvertResult exitoso

- GIVEN un `MarkitDownConverter` y un archivo `test.docx` válido
- WHEN se llama `converter.convert(Path("test.docx"))`
- THEN retorna `ConvertResult(content="...", metadata={"source": "test.docx", "format": "docx"}, success=True, error=None)`

#### Scenario: ARCH-01/02 — ConvertResult con error

- GIVEN un `MarkitDownConverter` y un archivo inexistente `no-existe.docx`
- WHEN se llama `converter.convert(Path("no-existe.docx"))`
- THEN retorna `ConvertResult(content="", metadata={}, success=False, error="File not found: no-existe.docx")`

#### Scenario: ARCH-03/04 — Registry lookup

- GIVEN el módulo `engine.py` importado
- WHEN se accede a `REGISTRY[".docx"]`
- THEN devuelve la clase `MarkitDownConverter`
- WHEN se accede a `REGISTRY[".doc"]`
- THEN devuelve la clase `LegacyPlaceholder`

#### Scenario: ARCH-05 — LegacyPlaceholder output

- GIVEN `LegacyPlaceholder` y un path `antiguo.doc`
- WHEN se llama `LegacyPlaceholder.convert(Path("antiguo.doc"))`
- THEN retorna `ConvertResult` con `success=False`
- AND `error` contiene "legacy format" y la solución (reconvertir a .docx)

---

## 5. build-packaging — Build y distribución

### Propósito

Script `scripts/build.ps1` que empaqueta `mid` como ejecutable portátil vía PyInstaller para Windows.

### Requirements

| ID | Requirement | Fuerza |
|---|---|---|
| BUILD-01 | El sistema DEBE incluir `scripts/build.ps1` que ejecute PyInstaller con spec apropiado | MUST |
| BUILD-02 | El build script DEBE generar `dist/mid.exe` funcional | MUST |
| BUILD-03 | El `mid.exe` generado DEBE poder convertir un archivo .docx real sin entorno Python | MUST |
| BUILD-04 | El build script DEBE aceptar flag `--clean` para rebuild limpio | SHOULD |
| BUILD-05 | El build script DEBE reportar éxito/fallo con exit code | MUST |

#### Scenario: BUILD-01/02 — Build exitoso

- GIVEN el proyecto con dependencias instaladas y PyInstaller disponible
- WHEN se ejecuta `scripts/build.ps1`
- THEN el script retorna exit code 0
- AND `dist/mid.exe` existe
- AND `dist/mid.exe` es un ejecutable Windows válido

#### Scenario: BUILD-03 — Ejecutable funcional

- GIVEN `dist/mid.exe` generado y un archivo `muestra.docx`
- WHEN se ejecuta `dist\mid.exe convert muestra.docx`
- THEN stdout contiene Markdown válido
- AND exit code es 0

#### Scenario: BUILD-05 — Falla por dependencia faltante

- GIVEN el proyecto sin PyInstaller instalado
- WHEN se ejecuta `scripts/build.ps1`
- THEN el script escribe error a stderr
- AND exit code es no-cero

---

## Criterios de Aceptación Globales

- [ ] `mid convert sample.docx` escribe Markdown a stdout (exit 0)
- [ ] `mid batch . -o out --recursive` procesa árbol completo (exit 0)
- [ ] `mid convert sample.docx --json` emite JSON parseable por `json.loads()`
- [ ] `mid convert legacy.doc` muestra error instructivo (exit 3)
- [ ] `mid --list-formats` lista los 7 formatos
- [ ] `mid --version` emite `mid 0.1.0`
- [ ] `mid convert inexistente.docx` retorna exit 2
- [ ] `scripts/build.ps1` genera `dist/mid.exe` funcional
