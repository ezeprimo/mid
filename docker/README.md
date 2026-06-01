# Docker Runtime for `mid`

## Overview

A lightweight Linux Docker image that runs the `mid` CLI. The container behaves as the `mid` command itself — mount your files and run conversions without installing Python or the `mid` package locally.

## Supported formats

| Format | Status |
|---|---|
| `.docx` | Supported |
| `.xlsx` | Supported |
| `.pptx` | Supported |
| `.pdf` | Supported |
| `.doc` / `.xls` / `.ppt` | Rejected (legacy Office — migrate first) |

## Build

```bash
docker build -f docker/Dockerfile -t mid .
```

## Run

### Single file conversion

```bash
docker run --rm \
  -v "$(pwd):/data" \
  mid convert /data/input.docx -o /data/output.md
```

### Batch conversion

```bash
docker run --rm \
  -v "$(pwd):/data" \
  mid batch /data/docs -o /data/out
```

### Recursive batch with structure preservation

```bash
docker run --rm \
  -v "$(pwd):/data" \
  mid batch /data/docs -o /data/out --recursive --preserve
```

### Interactive help

```bash
docker run --rm -v "$(pwd):/data" mid --help
docker run --rm -v "$(pwd):/data" mid --list-formats
```

Windows PowerShell example:

```powershell
docker run --rm -v D:\docs:/data mid convert /data/input.docx -o /data/output.md
```

## Volume mounts

The `/data` work directory is the working directory inside the container. Mount the host directory containing your files to `/data`:

- `-v /host/path:/data` — maps host path to container workdir
- Output paths inside the container are relative to `/data`, so `-o /data/out` writes to the mounted host directory

## Future extension: LibreOffice support

The current image is slim and focused on MarkItDown-based conversions (`.docx`, `.xlsx`, `.pptx`, `.pdf`).

For legacy `.doc` / `.xls` / `.ppt` conversion, a future image variant should add LibreOffice headless and a pre-conversion step:

1. Install LibreOffice in the image
2. Invoke `soffice --headless --convert-to ...` before running `mid`
3. Feed the converted `.docx` / `.xlsx` / `.pptx` output into the existing MarkItDown flow

This path is intentionally left out to keep the image small and fast for the supported format set.
