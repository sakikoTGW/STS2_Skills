# Maintainer release (GitHub CLI) — no custom Python upload script required.
# Prereqs: git tag pushed, gh auth login, optional sts2skill.exe built locally.
#
#   ./scripts/sync-version.ps1
#   ./scripts/release.ps1
#   ./scripts/release.ps1 -Tag v1.0.5 -SkipExe

param(
    [string]$Tag = "",
    [string]$Repo = "sakikoTGW/STS2_Skills",
    [switch]$SkipExe,
    [switch]$Draft
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

& "$PSScriptRoot/sync-version.ps1" -Check

$py = Get-Content "pyproject.toml" -Raw -Encoding UTF8
if ($py -notmatch '(?m)^version\s*=\s*"([^"]+)"') { throw "version missing in pyproject.toml" }
$ver = $Matches[1]
if (-not $Tag) { $Tag = "v$ver" }

python "$PSScriptRoot/build_release_assets.py" $Tag
$zip = Join-Path $root "dist/STS2_Skills-$Tag.zip"
if (-not (Test-Path $zip)) { throw "Missing $zip" }

$notesFile = Join-Path $root "CHANGELOG.md"
$notes = if (Test-Path $notesFile) {
    $raw = Get-Content $notesFile -Raw -Encoding UTF8
    if ($raw -match "(?ms)## \[$([regex]::Escape($ver))\].*?(?=## \[|\z)") { $Matches[0].Trim() }
    else { "Release $Tag — see CHANGELOG.md" }
} else { "Release $Tag" }

$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) { throw "Install GitHub CLI: https://cli.github.com/" }

$args = @("release", "create", $Tag, $zip, "--repo", $Repo, "--title", $Tag, "--notes", $notes)
if ($Draft) { $args += "--draft" }

$exe = Join-Path $root "sts2skill.exe"
if (-not $SkipExe -and (Test-Path $exe)) {
    $args += $exe
} elseif (-not $SkipExe) {
    Write-Warning "sts2skill.exe not found — upload exe separately or pass -SkipExe"
}

& gh @args
Write-Host "https://github.com/$Repo/releases/tag/$Tag"
