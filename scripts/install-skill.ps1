param(
    [ValidateSet("opencode", "claude", "agents", "all")]
    [string]$Runtime = "opencode",

    [ValidateSet("copy", "symlink")]
    [string]$Mode = "copy",

    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"

function Get-DefaultSkillDirectory {
    param([string]$Name)

    switch ($Name) {
        "opencode" { return (Join-Path $HOME ".config\opencode\skills") }
        "claude" { return (Join-Path $HOME ".claude\skills") }
        "agents" { return (Join-Path $HOME ".agents\skills") }
        default { throw "Unsupported runtime: $Name" }
    }
}

function Install-SkillDirectory {
    param(
        [string]$Name,
        [string]$BaseDirectory,
        [string]$SourceDirectory,
        [string]$InstallMode
    )

    $null = New-Item -ItemType Directory -Force -Path $BaseDirectory
    $targetDirectory = Join-Path $BaseDirectory "mid-cli"

    if (Test-Path -LiteralPath $targetDirectory) {
        Remove-Item -LiteralPath $targetDirectory -Recurse -Force
    }

    if ($InstallMode -eq "symlink") {
        try {
            New-Item -ItemType SymbolicLink -Path $targetDirectory -Target $SourceDirectory | Out-Null
        } catch {
            Write-Warning "Symlink creation failed (need admin/Developer Mode). Falling back to copy mode."
            Copy-Item -LiteralPath $SourceDirectory -Destination $targetDirectory -Recurse
            $InstallMode = "copy"
        }
    }
    else {
        Copy-Item -LiteralPath $SourceDirectory -Destination $targetDirectory -Recurse
    }

    Write-Host "Installed mid-cli skill for $Name -> $targetDirectory ($InstallMode)"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$sourceDirectory = Join-Path $repoRoot "skills\mid-cli"

if (-not (Test-Path -LiteralPath (Join-Path $sourceDirectory "SKILL.md"))) {
    throw "Source skill not found at $sourceDirectory"
}

if ($Destination -and $Runtime -eq "all") {
    throw "-Destination cannot be used with -Runtime all"
}

if ($Runtime -eq "all") {
    foreach ($name in @("opencode", "claude", "agents")) {
        Install-SkillDirectory -Name $name -BaseDirectory (Get-DefaultSkillDirectory $name) -SourceDirectory $sourceDirectory -InstallMode $Mode
    }
    exit 0
}

$targetBase = if ($Destination) { $Destination } else { Get-DefaultSkillDirectory $Runtime }
Install-SkillDirectory -Name $Runtime -BaseDirectory $targetBase -SourceDirectory $sourceDirectory -InstallMode $Mode
