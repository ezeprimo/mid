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

### Update checker

`mid` shows a non-intrusive update banner on stderr when a newer release is available:

```
Update available: 0.1.1 -> 0.2.0
  curl -fsSL https://raw.githubusercontent.com/ezeprimo/mid/main/install.sh | bash
  or: pipx install --force 'mid==0.2.0'
  https://github.com/ezeprimo/mid/releases
```

On Windows the installer line uses `irm https://raw.githubusercontent.com/ezeprimo/mid/main/install.ps1 | iex`.

Behavior:
- TTY only — no banner when stderr is not a terminal, when `CI` or `GITHUB_ACTIONS` is set, or when `TERM=dumb`.
- Throttled to one GitHub API check per 24 hours (cache at `platformdirs.user_cache_dir("mid")/update_cache.json` or `~/.config/mid/.update_cache.json`).
- Suppressed for `--help`/`-h`/`--version`, `--list-formats`, `--json`, and non-trunk commands.
- Never writes to stdout and never changes exit codes (0–3).
- Network timeout is 2 seconds; failures are silent.

Opt-out (any one is enough):
- `MID_NO_UPDATE_CHECK=1` (also accepts `true`/`yes`/`on`, case-insensitive)
- `CI=1` or `GITHUB_ACTIONS=1` or `TERM=dumb`

### Uninstall

Use the bootstrap uninstall scripts (same pattern as install — no admin/sudo required):

```powershell
# Windows
irm https://raw.githubusercontent.com/ezeprimo/mid/main/uninstall.ps1 | iex
```

```bash
# Linux
curl -fsSL https://raw.githubusercontent.com/ezeprimo/mid/main/uninstall.sh | bash
```

The uninstaller removes the `mid` binary, cleans up the installer PATH entry, removes install directories if empty, and removes the update checker cache file. Safe to run even if `mid` was partially installed or already removed. Uninstall scripts remove the cache file as well.

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

## Agent skill for `mid`

This repo ships a project-local agent skill for tools that support repo-distributed `SKILL.md` files.

### What it teaches

- when to use `mid` for document-to-Markdown conversion
- when to use the local `.venv` vs packaged binaries from `dist/`
- how to validate real conversions instead of shallow `--help` / `--version` checks
- which formats are supported vs intentionally rejected as legacy

### Skill location

- `skills/mid-cli/SKILL.md`

### Supporting reference

- `skills/mid-cli/references/usage.md`

### Suggested ways to consume it

1. If your agent runtime scans repo-local skills, open the repo and let it discover `skills/mid-cli/SKILL.md`.
2. If your runtime uses a personal skills directory, copy or symlink the `skills/mid-cli/` folder into that directory.
3. Reload or restart your agent runtime after installing the skill so it refreshes skill discovery.

### Optional installer helpers

Linux / macOS / WSL:

```bash
bash ./scripts/install-skill.sh opencode
bash ./scripts/install-skill.sh claude --mode symlink
bash ./scripts/install-skill.sh agents
```

Windows PowerShell:

```powershell
./scripts/install-skill.ps1 -Runtime opencode
./scripts/install-skill.ps1 -Runtime claude -Mode symlink
./scripts/install-skill.ps1 -Runtime agents
```

These helpers install the `mid-cli` skill into the default global skill directories for:

- OpenCode: `~/.config/opencode/skills/mid-cli`
- Claude-compatible external skills: `~/.claude/skills/mid-cli`
- Agents-compatible external skills: `~/.agents/skills/mid-cli`

Restart the target runtime after installation so it reloads skills.

This skill is distributed with the repo on purpose: agents should learn the real `mid` workflow from the source project, including `.venv` usage, release-installer limits, and real conversion validation.

## Docker

Container resources live under `docker/`.

The Docker image now uses a multi-stage build: the builder stage compiles a standalone Linux binary with PyInstaller, and the runtime stage ships only the `mid` command on `debian:bookworm-slim`.

### Build

```bash
docker build -f docker/Dockerfile -t mid .
```

### Usage

Mount your host documents as a volume and refer to them with container paths:

```bash
# Show help and version
docker run --rm mid
docker run --rm mid --version
docker run --rm mid --list-formats

# Convert a single file (mount the directory containing your file)
docker run --rm -v /path/to/docs:/docs mid convert /docs/report.docx -o /docs/report.md

# Batch convert a directory
docker run --rm -v /path/to/docs:/docs mid batch /docs -o /docs/out --recursive --preserve
```

> On Windows PowerShell, volume paths use the host syntax:
> `docker run --rm -v D:\docs:/docs mid batch /docs`

For the detailed Docker guide and future LibreOffice extension notes, see `docker/README.md`.

### Future: legacy format support

Add LibreOffice to the image to unlock `.doc`, `.xls`, `.ppt` conversion:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-common libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*
```

Rebuild and run — no other configuration needed. The image is structured with this extension point ready.

## Current status and scope

- Early-stage CLI project focused on reliable document-to-Markdown conversion.
- Scope is currently local CLI usage and conversion workflow ergonomics.
- GitHub repository metadata and publication setup are handled separately from this package.
