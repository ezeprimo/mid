# syntax=docker/dockerfile:1

# ============================================================
# Builder stage: build mid Linux binary with PyInstaller
# ============================================================
FROM python:3.12-slim-bookworm AS builder

LABEL maintainer="ezeprimo"
LABEL description="mid CLI - Document to Markdown converter using Microsoft MarkItDown"

WORKDIR /build

# PyInstaller requires objdump on Linux.
RUN apt-get update \
    && apt-get install -y --no-install-recommends binutils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip \
    && pip install --no-cache-dir pyinstaller "markitdown[all]"

COPY pyproject.toml ./
COPY src/ src/

RUN python -m PyInstaller --onefile --name mid-linux-amd64 --clean \
    --paths src \
    --hidden-import markitdown \
    --collect-data magika \
    --exclude-module torch \
    --exclude-module tensorflow \
    --exclude-module transformers \
    --exclude-module scipy \
    --exclude-module matplotlib \
    --exclude-module IPython \
    --exclude-module jedi \
    --exclude-module zmq \
    --exclude-module pytest \
    --distpath dist \
    --workpath build \
    --specpath . \
    src/mid/__main__.py

# ============================================================
# Runtime stage: minimal image with just the mid command
# ============================================================
FROM debian:bookworm-slim

LABEL maintainer="ezeprimo"
LABEL description="mid CLI - Document to Markdown converter using Microsoft MarkItDown"

# Future: install LibreOffice packages here for legacy pre-conversion.

RUN adduser --disabled-password --gecos "" mid

COPY --from=builder /build/dist/mid-linux-amd64 /usr/local/bin/mid
RUN chmod +x /usr/local/bin/mid

USER mid
WORKDIR /workspace

ENTRYPOINT ["mid"]
CMD ["--help"]
