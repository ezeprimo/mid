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

`--json` also carries a `timings` object, with the same four keys on every route:

```json
"timings": { "detection_ms": 0, "probe_ms": 0, "conversion_ms": 41, "total_ms": 46 }
```

All values are integer milliseconds (truncated). `detection_ms` covers format resolution and backend lookup,
`probe_ms` the availability probes (`0` on the native path, which never probes) and `conversion_ms` the conversion
itself. `total_ms` is the wall clock over the whole command, so the three stages are a subset of it
(`detection_ms + probe_ms + conversion_ms <= total_ms`), never a sum. Read the stage timings to tell a stuck probe
from a slow conversion instead of guessing from the total.

## Batch conversion

```bash
# Convert all supported files in a directory (non-recursive)
mid batch ./docs -o ./out

# Recursive with preserved directory structure
mid batch ./docs -o ./out --recursive --preserve

# Recursive with flattened output (no subdirectories)
mid batch ./docs -o ./out --recursive --flatten

# Machine-readable summary with timings
mid batch ./docs -o ./out --json
```

`--json` prints exactly one JSON document to stdout; the human `Processed: ...` line is suppressed, per-file `error:`
lines stay on stderr, and exit `1` still means at least one file failed. Shape:

```json
{
  "processed": 2, "succeeded": 1, "failed": 1, "skipped": 0,
  "timings": { "total_ms": 120, "worst_ms": 82, "p50_ms": 41 },
  "files": [
    { "source": "a.docx", "success": true, "error": null,
      "timings": { "detection_ms": 0, "probe_ms": 0, "conversion_ms": 40, "total_ms": 41 } },
    { "source": "b.pdf", "success": false, "error": "unsupported format .pdf",
      "timings": { "detection_ms": 0, "probe_ms": 0, "conversion_ms": 81, "total_ms": 82 } }
  ]
}
```

Per-file `timings.total_ms` is the measured wall clock of that file's conversion; `worst_ms` is the slowest file and
`p50_ms` the median, both integer milliseconds, with `total_ms >= worst_ms`. No file content is included.

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

Windows with installed Office (`mid doctor` shows `backend:office` ok):

```powershell
mid convert .\legacy\report.doc --backend office -o .\out\report.md
mid convert .\legacy\deck.ppt  --backend office -o .\out\deck.md
```

`.ppt` goes through PowerPoint COM. PowerPoint is single-instance, so if a running `POWERPNT.exe` already holds
presentations the command exits `3` before opening, saving or quitting anything (your unsaved work is never closed) —
close PowerPoint and retry, or use `--backend libreoffice`. `mid batch` counts that file as `Failed` and exits `1`.
The PowerPoint window is visible during conversion (PowerPoint refuses `Visible = False`); it is not a headless path.

## Format guidance

- Supported production formats are those reported by `mid --list-formats` under the `Supported:` line.
- Formats on the `Via backend (auto-detected):` line (`.odt`, `.ods`, `.odp`, `.rtf`) are auto-routed to an installed
  backend, so `mid convert report.odt` works without `--backend libreoffice`. Without the backend the exit is 3 and the
  message names the backend, the reason and the install hint.
- Legacy formats `.doc`, `.xls`, `.ppt` are rejected by default but convertible via a legacy backend (see above).
- Exception: on Windows with the `office` backend available (`mid doctor` shows `backend:office` ok — listing with `--list-backends` never probes opt-in backends), `.doc`/`.xls`/`.ppt` convert via `mid convert <file> --backend office` (see `docs/office-backend.md`).

```powershell
mid doctor
mid convert .\legacy\report.doc --backend office -o .\out\report.md
mid convert .\legacy\deck.ppt --backend office -o .\out\deck.md
```

For the authoritative list at runtime, run `mid --list-formats`.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Conversion error (MarkItDown / converter failure, incl. legacy conversion failure) |
| 2 | Argument error (missing file, invalid flag, unknown backend) |
| 3 | Unsupported format, or unavailable backend when `--backend` names one that is not installed. `convert --backend office` also uses `3` when PowerPoint already has presentations open (shared single instance); `batch` counts that file as `Failed` and exits `1`. |

## Inline help

```bash
mid help convert
mid help batch
mid --list-formats
```
