# mid CLI agent usage reference

## Repo development flow

Use the project-local environment for source-based work:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e . "markitdown[all]"
mid --help
mid convert ./tmp/sample.docx -o ./tmp/sample.md
```

Windows PowerShell activation:

```powershell
./.venv/Scripts/Activate.ps1
python -m pip install -e . "markitdown[all]"
mid convert .\tmp\sample.docx -o .\tmp\sample.md
```

## Packaged binary validation

Linux / WSL:

```bash
chmod +x scripts/build.sh
bash ./scripts/build.sh --clean --output-dir dist
./dist/mid-linux-amd64 --version
./dist/mid-linux-amd64 convert ./tmp/sample.docx -o ./tmp/sample.md
```

Windows PowerShell:

```powershell
./scripts/build.ps1 -Clean -OutputDir dist
.\dist\mid-windows-amd64.exe --version
.\dist\mid-windows-amd64.exe convert .\tmp\sample.docx -o .\tmp\sample.md
```

Do not stop at `--version` or `--help`. A valid packaging check requires a real conversion.

## Published release install flow

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

- Supported modern formats for this project contract: `.docx`, `.xlsx`, `.pptx`, `.pdf`
- Legacy formats intentionally rejected: `.doc`, `.xls`, `.ppt`

If the task is to prove support, use a real sample file and inspect the generated Markdown.
