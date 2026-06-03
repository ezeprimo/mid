<#
.SYNOPSIS
    Build mid Windows release executable with PyInstaller.
.DESCRIPTION
    Creates a single-file executable `mid-windows-amd64.exe` via PyInstaller.
    Hidden imports are resolved empirically -- if runtime fails with ImportError,
    add the missing module to $HIDDEN_IMPORTS and rebuild.

    Usage:
        .\scripts\build.ps1
        .\scripts\build.ps1 -Clean
        .\scripts\build.ps1 -Version v1.2.3 -OutputDir dist
.PARAMETER Clean
    Remove previous build artifacts before building.
.PARAMETER Version
    Optional CI tag/version (vX.Y.Z or X.Y.Z) validated against package version.
.PARAMETER OutputDir
    Destination directory for output artifact.
#>

param(
    [switch]$Clean = $false,
    [string]$Version = "",
    [string]$OutputDir = "dist"
)

if (-not $OutputDir) { throw "-OutputDir cannot be empty" }

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $VenvPython) {
    $PythonExe = $VenvPython
    Write-Host "Using project-local Python: $PythonExe"
} else {
    $PythonExe = (Get-Command python -ErrorAction Stop).Source
    Write-Host "Using system Python: $PythonExe"
}

& $PythonExe -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not available in $PythonExe. Install it in the project .venv for reproducible builds."
}

if ($Version.StartsWith("v")) {
    $Version = $Version.Substring(1)
}

if ($Version) {
    $packageVersion = (& $PythonExe -c "from pathlib import Path; ns={}; exec(Path('src/mid/__init__.py').read_text(encoding='utf-8'), ns); print(ns['__version__'])").Trim()
    if ($Version -ne $packageVersion) {
        throw "Version mismatch: expected $Version but package is $packageVersion"
    }
}

# ---- clean -----------------------------------------------------------------
if ($Clean -or (Test-Path "build") -or (Test-Path $OutputDir)) {
    Write-Host "Cleaning previous build artifacts..."
    Remove-Item -Recurse -Force "build", $OutputDir -ErrorAction SilentlyContinue
    Remove-Item "mid-windows-amd64.spec" -ErrorAction SilentlyContinue
}

# ---- prerequisites ---------------------------------------------------------
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Host "Building mid-windows-amd64.exe ..."

# Hidden imports discovered empirically.
$HIDDEN_IMPORTS = @(
    "--hidden-import", "markitdown"
    "--hidden-import", "numpy._core._exceptions"
)

# Runtime data needed by MarkItDown dependencies.
$COLLECT_DATA = @(
    "--collect-data", "magika"
)

# Exclude heavy packages present in data-science environments but unused by mid.
$EXCLUDES = @(
    "--exclude-module", "torch"
    "--exclude-module", "tensorflow"
    "--exclude-module", "transformers"
    "--exclude-module", "scipy"
    "--exclude-module", "matplotlib"
    "--exclude-module", "IPython"
    "--exclude-module", "jedi"
    "--exclude-module", "zmq"
    "--exclude-module", "pytest"
)

# ---- build -----------------------------------------------------------------
& $PythonExe -m PyInstaller --onefile --name mid-windows-amd64 --clean `
    --paths src `
    $HIDDEN_IMPORTS `
    $COLLECT_DATA `
    $EXCLUDES `
    --distpath $OutputDir `
    --workpath build `
    --specpath . `
    src/mid/__main__.py

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    $artifact = Join-Path $OutputDir "mid-windows-amd64.exe"
    $size = (Get-Item $artifact).Length / 1MB
    Write-Host ("SUCCESS: " + $artifact + " created (" + [math]::Round($size, 1) + " MB)")
} else {
    Write-Error ("BUILD FAILED (exit " + $exitCode + ")")
}

exit $exitCode
