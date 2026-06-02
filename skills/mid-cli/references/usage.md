# mid CLI agent usage reference

## Verify installation

```bash
mid --version
mid --list-formats
```

If `mid` is not found, see [Install from Release](#install-from-release).

## Single-file conversion

```bash
# Write output to stdout
mid convert ./docs/report.docx

# Write output to a file
mid convert ./docs/report.docx -o ./out/report.md

# Emit JSON with metadata (content under "content" key)
mid convert ./docs/report.docx --json
```

When `-o` is absent, output goes to stdout. When `-o` is provided, content is written to the specified file. The `--json` flag wraps content and metadata in a structured JSON payload regardless of `-o`. When `--json` is provided, output always goes to stdout and any `-o` flag is silently ignored.

## Batch conversion

```bash
# Convert all supported files in a directory (non-recursive)
mid batch ./docs -o ./out

# Recursive with preserved directory structure
mid batch ./docs -o ./out --recursive --preserve

# Recursive with flattened output (no subdirectories)
mid batch ./docs -o ./out --recursive --flatten
```

Flag constraints:
- `--recursive` requires `--preserve` or `--flatten` (to prevent data loss from overwrites).
- `--flatten` **requires** `--recursive` (error if used alone).
- `--preserve` requires `--recursive` (error if used alone).
- `-o / --output` is required for batch mode.

## Install from Release

Use bootstrap installers only when the requested version exists as a GitHub Release.

Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/ezeprimo/mid/main/install.sh | bash
MID_VERSION=v1.2.3 curl -fsSL https://raw.githubusercontent.com/ezeprimo/mid/main/install.sh | bash
```

Windows:

```powershell
irm https://raw.githubusercontent.com/ezeprimo/mid/main/install.ps1 | iex
$env:MID_VERSION = "v1.2.3"
irm https://raw.githubusercontent.com/ezeprimo/mid/main/install.ps1 | iex
```

## Format guidance

- Supported production formats are those reported by `mid --list-formats` under the `Supported:` line.
- Legacy formats intentionally rejected: `.doc`, `.xls`, `.ppt`

For the authoritative list at runtime, run `mid --list-formats`.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Conversion error (MarkItDown / converter failure) |
| 2 | Argument error (missing file, invalid flag, etc.) |
| 3 | Unsupported format (including legacy `.doc` / `.xls` / `.ppt`) |

## Inline help

```bash
mid help convert
mid help batch
mid --list-formats
```
