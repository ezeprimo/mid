# mid

`mid` is a small CLI that converts documents to Markdown using Microsoft MarkItDown.
It provides a consistent command surface for single-file and batch conversion workflows.

## Quick start

Create and activate a local virtual environment:

```bash
python -m venv .venv
```

- **Windows (PowerShell):** `./.venv/Scripts/Activate.ps1`
- **macOS/Linux:** `source .venv/bin/activate`

Install the project and recommended conversion extras:

```bash
python -m pip install --upgrade pip
python -m pip install -e . "markitdown[all]"
```

Check the CLI:

```bash
mid --help
```

## Core commands

```bash
# Show version and supported formats
mid --version
mid --list-formats

# Convert one file
mid convert ./docs/report.docx
mid convert ./docs/report.docx -o ./out/report.md

# Convert a directory
mid batch ./docs -o ./out
mid batch ./docs -o ./out --recursive --preserve
```

## Supported formats

### Conversion formats

- `.docx`
- `.xlsx`
- `.pptx`
- `.pdf`

### Legacy formats (explicitly handled)

- `.doc`
- `.xls`
- `.ppt`

Legacy Office formats are currently detected and rejected with a clear message to migrate to modern formats first.

> Real conversion capability depends on installed MarkItDown extras and system tools.
> For this repo, `markitdown[all]` inside local `.venv` is the recommended setup.

## Development and testing (local `.venv`)

Use the project-local virtual environment for all Python commands:

```bash
./.venv/Scripts/python -m pip install -e . "markitdown[all]"
./.venv/Scripts/python -m pip install pytest
./.venv/Scripts/python -m pytest
```

The test suite includes mocked converter tests and real end-to-end `.docx` conversion checks.

## Current status and scope

- Early-stage CLI project focused on reliable document-to-Markdown conversion.
- Scope is currently local CLI usage and conversion workflow ergonomics.
- GitHub repository metadata and publication setup are handled separately from this package.
