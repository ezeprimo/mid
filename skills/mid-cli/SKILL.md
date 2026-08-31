---
name: mid-cli
description: "Trigger: mid, MarkItDown, convert document to markdown, .docx, .pdf, batch conversion. Use this skill when an agent needs to run or validate the mid CLI correctly."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "2.0"
---

# mid CLI

## Activation Contract

Use this skill when working with the `mid` document-to-Markdown CLI: installing `mid`, running single-file conversions, processing batch directories, validating supported formats, or helping users use `mid` correctly.

## Hard Rules

- Always verify a real conversion, not only `--help` or `--version`.
- Use `mid --list-formats` to discover supported formats at runtime.
- When `-o` is absent, output goes to stdout; use `-o <file>` to write to file.
- Check exit codes: 0 success, 1 conversion error, 2 argument error, 3 unsupported format.
- If `mid` is not found on PATH, install via bootstrap installer.
- Supported production formats are those reported by `mid --list-formats` under the `Supported:` line.
- Legacy Office formats `.doc`, `.xls`, and `.ppt` are intentionally rejected; report that users must migrate them first.

## Decision Gates

| Situation | Action |
| --- | --- |
| `mid` not found on PATH | Install via bootstrap installer. |
| Single file conversion | `mid convert <file> [-o <output>] [--json]` |
| Batch directory conversion | `mid batch <input> -o <output> [--recursive --preserve\|--recursive --flatten]` |
| Check supported formats | `mid --list-formats` |
| Need inline help | `mid help <command>` |
| Legacy `.doc/.xls/.ppt` input | Stop and explain the format is intentionally unsupported for conversion. |

## Execution Steps

1. Check if `mid` is installed: `mid --version`. If found, use the system binary.
2. If not found, install via bootstrap installer.
3. For single file: `mid convert <file> [-o <output>] [--json]`
4. For batch: `mid batch <dir> -o <outdir> [--recursive --preserve | --recursive --flatten]`
5. Always verify a real conversion works (not just `--help`).
6. Use exit codes to decide next action.

## Update Checker

- `mid` prints an update banner to **stderr only** when a newer GitHub Release exists (TTY, 24h throttle).
- Banner is suppressed on `--help`/`-h`/`--version`, `--list-formats`, `--json`, non-TTY, `CI`/`GITHUB_ACTIONS`/`TERM=dumb`, or non-trunk commands.
- Opt-out: `MID_NO_UPDATE_CHECK=1` (also `true`/`yes`/`on`, case-insensitive).
- Cache: `platformdirs.user_cache_dir("mid")/update_cache.json` fallback `~/.config/mid/.update_cache.json`, perms 0700/0600, 24h `CACHE_TTL=86400`.

## Output Contract

Return how `mid` was resolved (binary path from `which mid` or `where mid`, `mid --version` output), the exact command executed, the input/output paths, whether the conversion was real or mocked, and any warnings or issues found.

## References

- `skills/mid-cli/references/usage.md` — canonical command patterns for installation, single-file, batch, and release usage.
- `README.md` — public CLI usage, supported formats, and install flows.
