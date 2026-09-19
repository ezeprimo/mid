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
- `--backend` is `convert`-only; `batch` has no backend flag — legacy files fail in batch mode, convert them individually (see below).

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

## Legacy backends (.doc / .xls / .ppt)

```bash
# Discover backend availability (2s never-raise probe)
mid --list-backends

# Convert via local headless LibreOffice
mid convert ./docs/report.doc --backend libreoffice -o ./out/report.md

# Convert via Docker legacy image (no local install)
docker build -f docker/Dockerfile.legacy -t mid:legacy .
docker run --rm -v "$(pwd)/tests/fixtures/legacy:/data" mid:legacy convert --backend libreoffice /data/sample.doc -o /data/out.md
```

Notes: local conversion needs `soffice` on PATH (`MID_LIBREOFFICE_PATH` override, `MID_LIBREOFFICE_TIMEOUT` default 30s, 5..300). The mounted host dir must be writable by container `USER mid` (`chmod a+rwX <host-dir>`). On LibreOffice 7.4, `.doc` converts but `.xls`/`.ppt` yield empty output.

## Format guidance

- Supported production formats are those reported by `mid --list-formats` under the `Supported:` line.
- Legacy formats `.doc`, `.xls`, `.ppt` are rejected by default but convertible via a legacy backend (see above).
- Exception: on Windows with the `office` backend available, `.doc`/`.xls` convert via `mid convert <file> --backend office` (see `docs/office-backend.md`). `.ppt` always stays migrate-first.

```powershell
mid --list-backends
mid convert .\legacy\report.doc --backend office -o .\out\report.md
```

For the authoritative list at runtime, run `mid --list-formats`.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Conversion error (MarkItDown / converter failure, incl. legacy conversion failure) |
| 2 | Argument error (missing file, invalid flag, unknown backend) |
| 3 | Unsupported format, or unavailable backend when `--backend` names one that is not installed |

## Inline help

```bash
mid help convert
mid help batch
mid --list-formats
```
