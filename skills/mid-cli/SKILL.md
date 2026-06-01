---
name: mid-cli
description: "Trigger: mid, MarkItDown, convert document to markdown, .docx, .pdf, batch conversion. Use this skill when an agent needs to run or validate the mid CLI correctly."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

# mid CLI

## Activation Contract

Use this skill when working with the `mid` document-to-Markdown CLI: running conversions, validating supported formats, checking packaged binaries, or helping users install and use `mid` correctly.

## Hard Rules

- In this repo, use the project-local `.venv` for Python commands and dependency installs.
- For repo development, prefer `python -m mid` or the editable install inside `.venv`; do not claim release installers work unless a real GitHub Release exists.
- For packaging validation, run the built binary from `dist/` and prove a real conversion works, not only `--help` or `--version`.
- Supported production formats are `.docx`, `.xlsx`, `.pptx`, and `.pdf`.
- Legacy Office formats `.doc`, `.xls`, and `.ppt` are intentionally rejected; report that users must migrate them first.
- Keep temporary inputs and outputs under a temp/work directory, never in the repo root.

## Decision Gates

| Situation | Action |
| --- | --- |
| Repo development or tests | Activate `.venv`, install editable package, run `mid` from local Python environment. |
| Linux/WSL packaging validation | Build `dist/mid-linux-amd64`, then run a real conversion with that binary. |
| Windows packaging validation | Build `dist/mid-windows-amd64.exe`, then run a real conversion with that executable. |
| User asks for bootstrap install | Use `install.sh` or `install.ps1` only for published releases. |
| Legacy `.doc/.xls/.ppt` input | Stop and explain the format is intentionally unsupported for conversion. |

## Execution Steps

1. Identify whether the task is repo development, local binary validation, or published-release installation.
2. Choose the runtime:
   - repo/dev: local `.venv`
   - packaging check: `dist/` binary
   - published install: bootstrap script or package install
3. Verify the CLI entry point with `mid --help` or `--version`, then run the real conversion command.
4. Prefer explicit output paths such as `mid convert input.docx -o ./tmp/output.md`.
5. Inspect the generated Markdown and report whether content, output file creation, and format handling behaved correctly.
6. If conversion fails, report the concrete runtime dependency or packaging issue instead of claiming the format is unsupported.

## Output Contract

Return the runtime used (`.venv`, built binary, or release install), the exact command executed, the input/output paths, whether the conversion was real or mocked, and any warnings or packaging gaps discovered.

## References

- `skills/mid-cli/references/usage.md` — canonical command patterns for repo, binary, and release usage.
- `README.md` — public CLI usage, supported formats, and install flows.
