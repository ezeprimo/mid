Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Repo = if ($env:MID_REPO) { $env:MID_REPO.Trim() } else { "ezeprimo/mid" }
$ApiBase = if ($env:MID_API_BASE) { $env:MID_API_BASE.TrimEnd('/') } else { "https://api.github.com" }
$RawBase = if ($env:MID_RAW_BASE) { $env:MID_RAW_BASE.TrimEnd('/') } else { "https://raw.githubusercontent.com" }
$RequestedVersionRaw = if ($env:MID_VERSION) { $env:MID_VERSION.Trim() } else { "latest" }
if (-not $RequestedVersionRaw) { $RequestedVersionRaw = "latest" }
$AssetName = "mid-windows-amd64.exe"
$ChecksumsAssetName = "checksums.txt"
$InstallDir = Join-Path $env:LOCALAPPDATA "mid\bin"
$TargetPath = Join-Path $InstallDir "mid.exe"
$SmokePattern = if ($env:MID_SMOKE_PATTERN) { $env:MID_SMOKE_PATTERN } else { "mid" }
$DisablePersistentPathUpdate = $env:MID_DISABLE_PERSIST_PATH_UPDATE -eq "1"

function Normalize-RequestedVersion([string]$Version) {
    if ($Version -eq "latest") { return "latest" }
    if ($Version.StartsWith("v")) { return $Version }
    return "v$Version"
}
function Get-GitHubRelease([string]$Repository, [string]$RequestedTag, [string]$ApiBaseUrl) {
    $headers = @{ "Accept" = "application/vnd.github+json"; "User-Agent" = "mid-installer" }
    $uri = if ($RequestedTag -eq "latest") { "$ApiBaseUrl/repos/$Repository/releases/latest" } else { "$ApiBaseUrl/repos/$Repository/releases/tags/$RequestedTag" }
    try { return Invoke-RestMethod -Method Get -Uri $uri -Headers $headers } catch { throw "Unable to resolve release '$RequestedTag' from '$Repository'. $($_.Exception.Message)" }
}
function Get-ReleaseAssetUrl([object]$Release, [string]$Name) {
    foreach ($asset in $Release.assets) { if ($asset.name -eq $Name) { return [string]$asset.browser_download_url } }
    throw "Release $($Release.tag_name) is missing asset '$Name'."
}
function Get-ExpectedChecksum([string]$ChecksumsPath, [string]$RequiredAssetName) {
    foreach ($line in (Get-Content -LiteralPath $ChecksumsPath)) {
        if ($line -match "^([a-fA-F0-9]{64})\s+\*?(.+)$" -and $Matches[2].TrimStart('* ').Trim() -eq $RequiredAssetName) { return $Matches[1].ToLowerInvariant() }
    }
    throw "checksums.txt is missing an entry for '$RequiredAssetName'."
}
function Write-NextSteps([string]$ResolvedTag, [string]$Repository, [string]$RawBaseUrl, [string]$Reason = "") {
    $PackageVersion = $ResolvedTag.TrimStart("v")
    $InstallScriptUrl = "$RawBaseUrl/$Repository/$ResolvedTag/install.ps1"
    if ($Reason) { Write-Warning "Binary install stopped: $Reason"; Write-Host ""; Write-Host "Fallback with the same version target ($ResolvedTag):"; Write-Host "  pipx install --force 'mid==$PackageVersion'"; Write-Host "  python -m pip install --user 'mid==$PackageVersion'"; Write-Host "" }
    Write-Host "Update to latest stable:"; Write-Host "  Remove-Item Env:MID_VERSION -ErrorAction SilentlyContinue"; Write-Host "  irm $InstallScriptUrl | iex"; Write-Host ""
    Write-Host "Rollback to a pinned version:"; Write-Host "  `$env:MID_VERSION = 'vX.Y.Z'"; Write-Host "  irm $InstallScriptUrl | iex"; Write-Host ""
    Write-Host "Uninstall with dedicated script (recommended):"; Write-Host "  irm $RawBaseUrl/$Repository/main/uninstall.ps1 | iex"; Write-Host ""; Write-Host "Phase-1 uninstall (manual fallback):"; Write-Host "  Remove-Item -LiteralPath '$TargetPath' -Force -ErrorAction SilentlyContinue"; Write-Host "  Remove user PATH entry '$InstallDir' if you no longer need it"
}
function Install-Atomically([string]$DownloadedPath, [string]$FinalPath) {
    $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $FinalPath)
    if (Test-Path -LiteralPath $FinalPath) {
        $backup = "$FinalPath.bak"; [System.IO.File]::Replace($DownloadedPath, $FinalPath, $backup, $true)
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
        return
    }
    Move-Item -LiteralPath $DownloadedPath -Destination $FinalPath -Force
}
function Ensure-UserPathContains([string]$PathEntry) {
    if ($DisablePersistentPathUpdate) { return "disabled" }
    $current = [Environment]::GetEnvironmentVariable("Path", "User"); if (-not $current) { $current = "" }
    foreach ($entry in @($current.Split(';', [System.StringSplitOptions]::RemoveEmptyEntries))) { if ($entry.TrimEnd('\\') -ieq $PathEntry.TrimEnd('\\')) { return "already-present" } }
    try { [Environment]::SetEnvironmentVariable("Path", ($(if ($current) { "$current;$PathEntry" } else { $PathEntry })), "User"); return "updated" } catch { return $_.Exception.Message }
}

$RequestedVersion = Normalize-RequestedVersion -Version $RequestedVersionRaw
$release = Get-GitHubRelease -Repository $Repo -RequestedTag $RequestedVersion -ApiBaseUrl $ApiBase
$ResolvedTag = [string]$release.tag_name
if (-not $ResolvedTag) { throw "Resolved release is missing tag_name." }
if ($RequestedVersion -ne "latest" -and $ResolvedTag -ne $RequestedVersion) { throw "Resolved tag '$ResolvedTag' does not match requested '$RequestedVersion'." }
$binaryUrl = Get-ReleaseAssetUrl -Release $release -Name $AssetName
$checksumsUrl = Get-ReleaseAssetUrl -Release $release -Name $ChecksumsAssetName
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("mid-installer-" + [Guid]::NewGuid().ToString("N"))
$null = New-Item -ItemType Directory -Path $tempRoot -Force
$downloadedBinary = Join-Path $tempRoot $AssetName
$downloadedChecksums = Join-Path $tempRoot $ChecksumsAssetName

try {
    Invoke-WebRequest -Uri $binaryUrl -OutFile $downloadedBinary
    Invoke-WebRequest -Uri $checksumsUrl -OutFile $downloadedChecksums
    $expectedHash = Get-ExpectedChecksum -ChecksumsPath $downloadedChecksums -RequiredAssetName $AssetName
    $actualHash = (Get-FileHash -LiteralPath $downloadedBinary -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expectedHash -ne $actualHash) { Write-NextSteps -ResolvedTag $ResolvedTag -Repository $Repo -RawBaseUrl $RawBase -Reason "SHA-256 mismatch for $AssetName"; exit 1 }
    if ($PSVersionTable.PSEdition -eq 'Core' -and ($IsLinux -or $IsMacOS)) { chmod +x $downloadedBinary }
    try { $versionOutput = (& $downloadedBinary --version 2>&1 | Out-String) } catch { Write-NextSteps -ResolvedTag $ResolvedTag -Repository $Repo -RawBaseUrl $RawBase -Reason "Binary smoke check failed (--version)."; exit 1 }
    if (-not $versionOutput -or $versionOutput -notmatch $SmokePattern) { Write-NextSteps -ResolvedTag $ResolvedTag -Repository $Repo -RawBaseUrl $RawBase -Reason "Unexpected binary output during smoke check."; exit 1 }

    Install-Atomically -DownloadedPath $downloadedBinary -FinalPath $TargetPath
    $pathResult = Ensure-UserPathContains -PathEntry $InstallDir
    $pathEntries = if ($env:Path) { $env:Path.Split(';', [System.StringSplitOptions]::RemoveEmptyEntries) } else { @() }
    if ($pathEntries -notcontains $InstallDir.TrimEnd('\')) {
        $env:Path = if ($env:Path) { "$InstallDir;$env:Path" } else { $InstallDir }
    }
    Write-Host "Installed mid $ResolvedTag to $TargetPath"
    if ($pathResult -eq "updated") { Write-Host "Added $InstallDir to user PATH. Open a new shell before running 'mid'." }
    elseif ($pathResult -eq "already-present") { Write-Host "User PATH already contains $InstallDir. Open a new shell if command is not yet visible." }
    elseif ($pathResult -eq "disabled") { Write-Host "Persistent PATH update disabled via MID_DISABLE_PERSIST_PATH_UPDATE." }
    else { Write-Warning "Could not update user PATH automatically: $pathResult"; Write-Host "Add this path manually and open a new shell:"; Write-Host "  $InstallDir" }
    Write-Host ""; Write-NextSteps -ResolvedTag $ResolvedTag -Repository $Repo -RawBaseUrl $RawBase
}
finally { if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue } }
