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

## Legacy variant with LibreOffice (`Dockerfile.legacy`, legacy only)

> **Legacy only.** This variant exists solely for `.doc` / `.xls` / `.ppt`
> conversion via headless LibreOffice. For `.docx` / `.xlsx` / `.pptx` /
> `.pdf`, use the slim image above.

The legacy image reuses the slim builder stage and adds a pinned
LibreOffice runtime wired to `mid convert --backend libreoffice`.
No display is required; conversions run fully headless.

### Build

```bash
docker build -f docker/Dockerfile.legacy -t mid:legacy .
```

### Run

List backends (must show `libreoffice: available`):

```bash
docker run --rm mid:legacy --list-backends
```

Mount conversion (copy-paste verbatim; `/data` is the container mount path):

```bash
docker run --rm -v "$(pwd)/tests/fixtures/legacy:/data" mid:legacy convert --backend libreoffice /data/sample.doc -o /data/out.md
```

Windows PowerShell example:

```powershell
docker run --rm -v ${PWD}\tests\fixtures\legacy:/data mid:legacy convert --backend libreoffice /data/sample.doc -o /data/out.md
```

> **Host directory permissions:** the image runs as non-root `USER mid`, so the mounted host directory must be writable by the container user — otherwise output writes fail with `Permission denied` (exit 1). On Linux/macOS: `chmod a+rwX <host-dir>` before mounting.

### Architecture, pins, resources

- Architecture: `linux/amd64`.
- Pinned packages (Debian bookworm, gated by implementation spike): `libreoffice-writer=4:7.4.7-1+deb12u14`, `libreoffice-calc=4:7.4.7-1+deb12u14`, `libreoffice-impress=4:7.4.7-1+deb12u14` (LibreOffice 7.4.7.2). Dependencies (e.g. `libreoffice-core`) resolve from the same snapshot via apt.
- Image size is ~1 GB (measured 1.01 GB); expect a slower first build and a few seconds of first-run LibreOffice profile latency per conversion.
- Runtime hardening matches the slim image: non-root `USER mid`, `ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 TMPDIR=/tmp HOME=/home/mid` with writable `HOME` for the soffice profile.
- Known limitation (spike result): on LibreOffice 7.4 the backend filter `html:XHTML Writer File:UTF8` converts `.doc` to non-empty Markdown but yields empty output for `.xls` / `.ppt` (backend reports conversion failure). CI smoke therefore covers the representative `.doc` path.

### Exit codes and logs

Exit codes pass through from `mid`: `0` success, `1` conversion failure, `2` argument error (e.g. unknown backend), `3` unsupported format or unavailable backend (with install hint on stderr). LibreOffice stderr is truncated to 500 chars in the error message; temporary files use `mid-libreoffice-*` under `TMPDIR` and are cleaned on success and failure.

## Volume mounts (slim image)

The `/data` work directory is the working directory inside the container. Mount the host directory containing your files to `/data`:

- `-v /host/path:/data` — maps host path to container workdir
- Output paths inside the container are relative to `/data`, so `-o /data/out` writes to the mounted host directory

## Legacy formats: use the legacy variant

The legacy variant described above (`docker/Dockerfile.legacy`, image
`mid:legacy`) is the supported path for `.doc` / `.xls` / `.ppt`
conversion via headless LibreOffice. The slim image stays focused on
MarkItDown-based conversions (`.docx`, `.xlsx`, `.pptx`, `.pdf`) to
keep it small and fast.
