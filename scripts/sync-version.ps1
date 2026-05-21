# Sync version from pyproject.toml (single source of truth) into other metadata files.
# Usage:
#   ./scripts/sync-version.ps1          # write changes
#   ./scripts/sync-version.ps1 -Check   # CI: fail if drift

param(
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$py = Get-Content "pyproject.toml" -Raw -Encoding UTF8
if ($py -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    throw "Could not read version from pyproject.toml"
}
$version = $Matches[1]
$tag = if ($version -match '^v') { $version } else { "v$version" }

function Set-Line {
    param([string]$Path, [string]$Pattern, [string]$Replacement)
    if (-not (Test-Path $Path)) { return $false }
    $text = Get-Content $Path -Raw -Encoding UTF8
    $new = [regex]::Replace($text, $Pattern, $Replacement, 1)
    if ($text -eq $new) { return $false }
    if ($Check) { return $true }
    Set-Content -Path $Path -Value $new -Encoding UTF8 -NoNewline
    return $true
}

$drift = $false

# plugin.yaml
if (Set-Line "plugins/sts2/plugin.yaml" '(?m)^version:\s*.+$' "version: $version") { $drift = $true }

# compat.yaml
if (Set-Line "compat.yaml" '(?m)^sts2_skills_version:\s*.+$' "sts2_skills_version: `"$version`"") { $drift = $true }

# AstrBot @register(..., version, ) before class Sts2AgentPlugin
$mainPy = "plugins/sts2/integrations/astrbot/plugin/main.py"
if (Test-Path $mainPy) {
    $t = Get-Content $mainPy -Raw -Encoding UTF8
    $newT = [regex]::Replace(
        $t,
        '(@register\([\s\S]*?\n\s+)"[\d.]+"(\s*\)\s*\r?\nclass Sts2AgentPlugin)',
        "`${1}`"$version`"`${2}",
        1
    )
    if ($t -ne $newT) {
        $drift = $true
        if (-not $Check) { Set-Content $mainPy $newT -Encoding UTF8 -NoNewline }
    }
}

# metadata.yaml (AstrBot marketplace)
$meta = "plugins/sts2/integrations/astrbot/plugin/metadata.yaml"
if (Test-Path $meta) {
    if (Set-Line $meta '(?m)^version:\s*.+$' "version: $version") { $drift = $true }
}

if ($Check) {
    if ($drift) {
        Write-Error "Version drift: run ./scripts/sync-version.ps1 and commit"
        exit 1
    }
    Write-Host "OK: all version files match pyproject.toml ($version)"
    exit 0
}

Write-Host "Synced version $version ($tag) from pyproject.toml"
