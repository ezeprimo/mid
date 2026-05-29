# mid

Small CLI wrapper around Microsoft MarkItDown for converting documents to Markdown.

## Quick start (local `.venv`)

```bash
python -m venv .venv
```

Activate the environment:

- **Windows (PowerShell):** `./.venv/Scripts/Activate.ps1`
- **macOS/Linux:** `source .venv/bin/activate`

Install project + recommended MarkItDown extras:

```bash
python -m pip install --upgrade pip
python -m pip install -e . "markitdown[all]"
```

## Usage

```bash
mid --help
mid --list-formats

mid convert ./docs/report.docx
mid convert ./docs/report.docx -o ./out/report.md

mid batch ./docs -o ./out
mid batch ./docs -o ./out --recursive --preserve
```

## Format support note

Real Office/PDF conversion capability depends on installed MarkItDown extras and system tools.
Recommended setup for this repo is `markitdown[all]` in local `.venv`.

## Troubleshooting

If you see an `ffmpeg` warning, it is usually from optional media-related paths and does **not** block normal `.docx` conversion.
