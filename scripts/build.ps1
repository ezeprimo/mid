<#
.SYNOPSIS
    Build mid.exe portable executable with PyInstaller.
.DESCRIPTION
    Creates a single-file executable dist/mid.exe via PyInstaller --onefile.
    Hidden imports are resolved empirically -- if the build succeeds but the
    exe fails at runtime with an ImportError, add the missing module to
    $HIDDEN_IMPORTS and rebuild.

    Usage:
        .\scripts\build.ps1          # normal build
        .\scripts\build.ps1 -Clean   # clean + rebuild
.PARAMETER Clean
    Remove previous build artifacts before building.
#>

param(
    [switch]$Clean = $false
)

$ErrorActionPreference = "Stop"

# ---- clean -----------------------------------------------------------------
if ($Clean -or (Test-Path "build") -or (Test-Path "dist")) {
    Write-Host "Cleaning previous build artifacts..."
    Remove-Item -Recurse -Force "build", "dist" -ErrorAction SilentlyContinue
    Remove-Item "mid.spec" -ErrorAction SilentlyContinue
}

# ---- prerequisites ---------------------------------------------------------
$null = Get-Command pyinstaller -ErrorAction Stop | Out-Null

Write-Host "Building mid.exe ..."

# Hidden imports discovered empirically during Phase 5.
# Add modules here when the built exe fails at runtime with ImportError.
$HIDDEN_IMPORTS = @(
    "--hidden-import", "markitdown"
)

# Exclude heavy packages present in data-science environments but unused by mid.
# Adjust this list if your environment has different heavy packages.
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
    "--exclude-module", "onnxruntime"
)

# ---- build -----------------------------------------------------------------
pyinstaller --onefile --name mid --clean `
    --paths src `
    $HIDDEN_IMPORTS `
    $EXCLUDES `
    --distpath dist `
    --workpath build `
    --specpath . `
    src/mid/__main__.py

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    $size = (Get-Item "dist/mid.exe").Length / 1MB
    Write-Host ("SUCCESS: dist/mid.exe created (" + [math]::Round($size, 1) + " MB)")
} else {
    Write-Error ("BUILD FAILED (exit " + $exitCode + ")")
}

exit $exitCode
