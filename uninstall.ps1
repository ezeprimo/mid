<#
.SYNOPSIS
    Uninstall mid CLI tool — reverse operation of install.ps1.
.DESCRIPTION
    Removes the mid binary, cleans up the User PATH entry, and removes
    the install directories (if empty).

    Safe to run even if mid was partially installed or already removed.
    Reports what was found and what was cleaned.

    Environment overrides:
      MID_REPO         — GitHub repo (default: ezeprimo/mid), used for docs only
      MID_INSTALL_DIR  — custom install directory (default: $env:LOCALAPPDATA\mid\bin);
                         not yet supported by install.ps1 — set manually if needed
.PARAMETER Force
    Skip confirmation prompts. Useful for automated/agent-driven uninstalls.
.PARAMETER DryRun
    Show what would be removed without actually deleting anything.
.EXAMPLE
    # Interactive uninstall
    .\uninstall.ps1

    # Automated uninstall
    .\uninstall.ps1 -Force

    # Preview only
    .\uninstall.ps1 -DryRun
#>

param(
    [switch]$Force = $false,
    [switch]$DryRun = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"   # don't stop on cleanup failures

$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { throw "LOCALAPPDATA environment variable is not set. Cannot determine install directory." }
$InstallDir = if ($env:MID_INSTALL_DIR) { $env:MID_INSTALL_DIR.Trim() } else { Join-Path $LocalAppData "mid\bin" }
$TargetPath = Join-Path $InstallDir "mid.exe"
$InstallParentDir = Split-Path -Parent $InstallDir   # e.g. $LocalAppData\mid
$Repo        = if ($env:MID_REPO) { $env:MID_REPO.Trim() } else { "ezeprimo/mid" }

$RemovedSomething = $false
$FoundIssues      = $false

function Write-Step([string]$Label) {
    Write-Host ""
    Write-Host ">> $Label" -ForegroundColor Cyan
}

function Write-Removed([string]$What) {
    Write-Host "  [removed] $What" -ForegroundColor Green
    $script:RemovedSomething = $true
}

function Write-Skipped([string]$What, [string]$Reason) {
    Write-Host "  [skipped] $What — $Reason" -ForegroundColor DarkYellow
}

function Write-NotFound([string]$What) {
    Write-Host "  [absent]  $What — nothing to clean" -ForegroundColor DarkGray
}

function Write-DryRun([string]$Action) {
    Write-Host "  [dry-run] would $Action" -ForegroundColor Magenta
}

# ---- preamble ---------------------------------------------------------------

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║       mid — Uninstall Script (Windows)   ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "Install dir : $InstallDir"
Write-Host "Binary      : $TargetPath"
Write-Host ""

if (-not $Force -and -not $DryRun) {
    Write-Host "This will remove mid from your system." -ForegroundColor Yellow
    $confirmation = Read-Host "Continue? [y/N]"
    if ($confirmation -notmatch '^(y|yes)$') {
        Write-Host "Uninstall cancelled." -ForegroundColor Yellow
        exit 0
    }
}

# ---- 1. Remove the binary ---------------------------------------------------

Write-Step "Binary"

if ($DryRun) {
    if (Test-Path -LiteralPath $TargetPath) {
        Write-DryRun "remove '$TargetPath'"
    } else {
        Write-NotFound $TargetPath
    }
} else {
    if (Test-Path -LiteralPath $TargetPath) {
        Remove-Item -LiteralPath $TargetPath -Force
        if (-not (Test-Path -LiteralPath $TargetPath)) {
            Write-Removed $TargetPath
        } else {
            Write-Warning "Could not delete '$TargetPath' — it may be in use or permissions insufficient."
            $FoundIssues = $true
        }
    } else {
        Write-NotFound $TargetPath
    }
}

# Also clean up any .bak file left by Install-Atomically (install.ps1)
$BackupPath = "$TargetPath.bak"
if ($DryRun) {
    if (Test-Path -LiteralPath $BackupPath) {
        Write-DryRun "remove '$BackupPath'"
    }
} elseif (Test-Path -LiteralPath $BackupPath) {
    Remove-Item -LiteralPath $BackupPath -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath $BackupPath)) {
        Write-Removed "$BackupPath (backup from atomic install)"
    } else {
        Write-Warning "Could not delete '$BackupPath'."
        $FoundIssues = $true
    }
}

# ---- 2. Update checker cache ------------------------------------------------

Write-Step "Update checker cache"

$cacheCandidates = @()
if ($env:LOCALAPPDATA) { $cacheCandidates += (Join-Path $env:LOCALAPPDATA "mid\update_cache.json") }
if ($env:XDG_CACHE_HOME) { $cacheCandidates += (Join-Path $env:XDG_CACHE_HOME "mid\update_cache.json") }
$cacheCandidates += (Join-Path $HOME ".cache\mid\update_cache.json")
$cacheCandidates += (Join-Path $HOME "Library\Caches\mid\update_cache.json")
if ($env:XDG_CONFIG_HOME) {
    $cacheCandidates += (Join-Path $env:XDG_CONFIG_HOME "mid\.update_cache.json")
    $cacheCandidates += (Join-Path $env:XDG_CONFIG_HOME "mid\update_cache.json")
}
$cacheCandidates += (Join-Path $HOME ".config\mid\.update_cache.json")
$cacheCandidates += (Join-Path $HOME ".config\mid\update_cache.json")

# Dedupe candidates
$seenCache = @{}
$uniqueCandidates = @()
foreach ($c in $cacheCandidates) {
    if (-not $c) { continue }
    if (-not $seenCache.ContainsKey($c)) {
        $seenCache[$c] = $true
        $uniqueCandidates += $c
    }
}

$removedParents = @()
foreach ($candidate in $uniqueCandidates) {
    if (Test-Path -LiteralPath $candidate) {
        if ($DryRun) {
            Write-DryRun "remove '$candidate' (update checker cache)"
            $removedParents += (Split-Path -Parent $candidate)
        } else {
            try { Remove-Item -LiteralPath $candidate -Force -ErrorAction SilentlyContinue } catch {}
            if (-not (Test-Path -LiteralPath $candidate)) {
                Write-Removed "'$candidate' (update checker cache)"
                $removedParents += (Split-Path -Parent $candidate)
            } else {
                Write-Warning "Could not delete '$candidate' (update checker cache)."
                $script:FoundIssues = $true
            }
        }
    }
}

# Try to remove empty parent directories bottom-up (best-effort)
if ($removedParents.Count -gt 0) {
    $seenParents = @{}
    $uniqueParents = @()
    foreach ($p in $removedParents) {
        if (-not $p) { continue }
        if (-not $seenParents.ContainsKey($p)) {
            $seenParents[$p] = $true
            $uniqueParents += $p
        }
    }
    foreach ($parent in $uniqueParents) {
        if (-not (Test-Path -LiteralPath $parent)) { continue }
        try {
            $children = @(Get-ChildItem -LiteralPath $parent -Force -ErrorAction SilentlyContinue)
            if ($DryRun) {
                $toRemove = @($uniqueCandidates | Where-Object { (Split-Path -Parent $_) -eq $parent -and (Test-Path -LiteralPath $_) }).Count
                $remaining = $children.Count - $toRemove
                if ($remaining -eq 0) {
                    Write-DryRun "remove empty directory '$parent' (update cache parent)"
                }
            } else {
                if ($children.Count -eq 0) {
                    Remove-Item -LiteralPath $parent -Force -ErrorAction SilentlyContinue
                    if (-not (Test-Path -LiteralPath $parent)) {
                        Write-Removed "empty directory '$parent' (update cache parent)"
                    } else {
                        Write-Skipped $parent "could not be removed"
                    }
                }
            }
        } catch {
            # silent on error
        }
    }
}

# ---- 3. Remove install directories (bottom-up) ------------------------------

Write-Step "Install directories"

foreach ($dir in @($InstallDir, $InstallParentDir)) {
    if ($DryRun) {
        if (Test-Path -LiteralPath $dir) {
            $children = @(Get-ChildItem -LiteralPath $dir -ErrorAction SilentlyContinue)
            if ($children.Count -eq 0) {
                Write-DryRun "remove empty directory '$dir'"
            } else {
                Write-DryRun "skip non-empty directory '$dir' ($($children.Count) items remain)"
            }
        }
        continue
    }

    if (-not (Test-Path -LiteralPath $dir)) {
        Write-NotFound $dir
        continue
    }

    $children = @(Get-ChildItem -LiteralPath $dir -ErrorAction SilentlyContinue)
    if ($children.Count -eq 0) {
        Remove-Item -LiteralPath $dir -Force
        if (-not (Test-Path -LiteralPath $dir)) {
            Write-Removed "empty directory '$dir'"
        } else {
            Write-Skipped $dir "could not be removed"
            $FoundIssues = $true
        }
    } else {
        Write-Skipped $dir "$($children.Count) item(s) remain — not mid-related"
    }
}

# ---- 4. Clean User PATH entry -----------------------------------------------

Write-Step "User PATH"

$currentPath = try { [Environment]::GetEnvironmentVariable("Path", "User") } catch { $null }
$normalizedEntry = $InstallDir.TrimEnd('\')

$pathEntries = if ($currentPath) {
    @($currentPath.Split(';', [System.StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object { $_.TrimEnd('\') })
} else {
    @()
}

$newEntries = $pathEntries | Where-Object { $_ -ne $normalizedEntry }
$removedCount = $pathEntries.Count - $newEntries.Count

if ($DryRun) {
    if ($removedCount -gt 0) {
        Write-DryRun "remove '$normalizedEntry' from User PATH ($removedCount occurrence(s))"
    } else {
        Write-NotFound "'$normalizedEntry' in User PATH"
    }
} else {
    if ($removedCount -gt 0) {
        $newPath = ($newEntries -join ';')

        # Avoid writing empty string to registry — set to $null to remove it
        if ([string]::IsNullOrEmpty($newPath)) {
            try {
                [Environment]::SetEnvironmentVariable("Path", $null, "User")
                Write-Removed "'$normalizedEntry' removed from User PATH (last entry — PATH variable removed)"
            } catch {
                Write-Warning "Could not remove User PATH from registry: $($_.Exception.Message)"
                $FoundIssues = $true
            }
        } else {
            try {
                [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
                Write-Removed "'$normalizedEntry' removed from User PATH"
            } catch {
                Write-Warning "Could not update User PATH: $($_.Exception.Message)"
                $FoundIssues = $true
            }
        }

        # Also remove from the current session PATH so the user doesn't have to restart
        try {
            $sessionPath = @($env:Path.Split(';', [System.StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object { $_.TrimEnd('\') })
            $newSessionPath = ($sessionPath | Where-Object { $_ -ne $normalizedEntry }) -join ';'
            if ([string]::IsNullOrEmpty($newSessionPath)) {
                $env:Path = $null
                Write-Host "  [info]    Also cleared from current session PATH (all entries removed)" -ForegroundColor DarkGray
            } else {
                $env:Path = $newSessionPath
                Write-Host "  [info]    Also removed from current session PATH" -ForegroundColor DarkGray
            }
        } catch {
            Write-Warning "Could not update session PATH: $($_.Exception.Message)"
            $FoundIssues = $true
        }
    } else {
        Write-NotFound "'$normalizedEntry' in User PATH"
    }
}

# ---- 5. Summary -------------------------------------------------------------

Write-Step "Done"

if ($DryRun) {
    Write-Host "Dry-run complete — no changes were made." -ForegroundColor Magenta
} elseif ($RemovedSomething) {
    Write-Host "mid has been uninstalled." -ForegroundColor Green
    if ($FoundIssues) {
        Write-Host "Some items could not be cleaned (see warnings above)." -ForegroundColor Yellow
    }
} else {
    Write-Host "Nothing to uninstall — mid was not found in the standard locations." -ForegroundColor DarkYellow
    Write-Host "If you installed mid to a custom location, remove it manually or set:" -ForegroundColor DarkYellow
    Write-Host "  `$env:MID_INSTALL_DIR = 'path\to\your\custom\dir'" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "Reinstall at any time:" -ForegroundColor Cyan
Write-Host "  irm https://raw.githubusercontent.com/$Repo/main/install.ps1 | iex" -ForegroundColor Cyan
