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

## Install from GitHub Releases (phase 1)

Use stable bootstrap installers (no admin/sudo required):

```powershell
# Windows (latest stable)
irm https://raw.githubusercontent.com/ezeprimo/mid/main/install.ps1 | iex

# Windows (pin / rollback to exact version)
$env:MID_VERSION = "v1.2.3"
irm https://raw.githubusercontent.com/ezeprimo/mid/main/install.ps1 | iex
```

```bash
# Linux (latest stable)
curl -fsSL https://raw.githubusercontent.com/ezeprimo/mid/main/install.sh | bash

# Linux (pin / rollback to exact version)
MID_VERSION=v1.2.3 curl -fsSL https://raw.githubusercontent.com/ezeprimo/mid/main/install.sh | bash
```

If binary integrity or compatibility checks fail, use fallback with the same version target:

```bash
pipx install --force "mid==1.2.3"
python -m pip install --user "mid==1.2.3"
```

### Update / rollback flow

- Update to latest stable: clear `MID_VERSION` and rerun the installer.
- Rollback: set `MID_VERSION=vX.Y.Z` and rerun the same installer command.

### Uninstall (phase 1)

- Windows: remove `%LOCALAPPDATA%\mid\bin\mid.exe` and remove `%LOCALAPPDATA%\mid\bin` from user PATH if you no longer need it.
- Linux: remove `${MID_INSTALL_DIR:-$HOME/.local/bin}/mid` and remove the installer PATH stanza from `~/.profile` (or your equivalent shell profile).

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
