# Office Backend (Windows)

Explicit opt-in backend that converts legacy Word/Excel files (`.doc`, `.xls`)
through an installed copy of Microsoft Office on Windows, via COM automation.
It mirrors the LibreOffice backend structure and error model.

> v1 scope: **Word/Excel only**. `.ppt` stays on the migrate-first path and
> is deferred post-v1.

## Quick path

```powershell
mid --list-backends
mid convert .\legacy\report.doc --backend office -o .\out\report.md
```

- `--backend office` is **always required** — the backend never activates silently.
- Without `--backend`, `.doc`/`.xls` keep the legacy migrate-first behavior.
- Unknown backend exits `2` (lists available backends); an unavailable
  `office` backend exits `3` with the detection reason.

## Supported versions and licensing

- Word/Excel 2016, 2019, 2021, and Microsoft 365 (Click-to-Run and MSI,
  32-bit and 64-bit).
- Office is **customer-provided** — `mid` never bundles or licenses Office.
- Requires the `office-windows` extra on Windows: `pip install "mid[office-windows]"`.
  `pywin32` is a lazy, Windows-only dependency and is never imported on
  Linux/macOS.

## Environment variables

| Variable | Meaning | Default / clamping |
| --- | --- | --- |
| `MID_OFFICE_PATH` | Override install signal; must be an existing file. Invalid values fall through to App Paths detection. The path is a version signal only — it is never executed. | unset |
| `MID_OFFICE_TIMEOUT` | Per-conversion timeout in seconds. | `30`, clamped to `5..300`; invalid values mean `30` |

Detection order (`probe()`, never raises, completes within 2s): platform gate
(`win32` only) → `MID_OFFICE_PATH` (existing file, invalid falls through) →
App Paths (`WINWORD.EXE`, then `EXCEL.EXE`) → `win32com` import → `HKCR\CurVer`
version. Only `available=True` results are cached.

## Security boundary

- Per-app `DispatchEx` only (`Word.Application`, `Excel.Application`) — never
  attaches to a running user instance (`Dispatch` is rejected).
- Documents open hidden and read-only; alerts, macros, DDE, and link updates
  are off (`DisplayAlerts=0`, `AutomationSecurity=3`, `AskToUpdateLinks=False`,
  `AddToRecentFiles=False`).
- Work happens in a `mid-office-` system temp dir that is always removed,
  including on timeouts.
- `Close` + `Quit` run in `finally`; hangs fall back to a PID-scoped kill
  (`GetWindowThreadProcessId` → `taskkill /F /PID`, `shell=False`). A
  `taskkill /IM` constrained to the allowlisted Office exes is fallback only.
  User-controlled paths are never executed.

## Limits

- Input extensions: `.doc`, `.xls` only (v1).
- HTML intermediate capped at 20 MB, strict UTF-8, then delegated to
  `MarkItDownConverter`.
- Headless/server sessions without an Office installation fail with an
  actionable `Office not detected` reason — no silent automation.

## Troubleshooting

| Symptom | Meaning | Action |
| --- | --- | --- |
| `unsupported platform` | Non-Windows host | Use the LibreOffice backend or convert on Windows |
| `Office not detected` | No App Paths entry / bad `MID_OFFICE_PATH` | Install Word/Excel or fix the env var |
| `pywin32 not installed` | Missing extra | `pip install "mid[office-windows]"` |
| `file locked — close Office` | File open elsewhere | Close Office and retry |
| `Office busy — retry` | RPC server busy | Retry shortly |
| `timed out after Ns (orphan cleaned up)` | Hung COM instance | Orphan was Quit + killed; retry |
| exit `2` / `3` | Unknown / unavailable backend | Check `--list-backends` output |
