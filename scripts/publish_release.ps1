# 已弃用：请使用 scripts/release.ps1（从 pyproject.toml 读版本 + CHANGELOG）
# 创建 GitHub Release 并上传 zip（需 gh 已登录）
param(
    [string]$Tag = "",
    [string]$Repo = "sakikoTGW/STS2_Skills",
    [string]$ZipPath = ""
)
$ErrorActionPreference = "Stop"
Write-Warning "Deprecated: use ./scripts/release.ps1"
$root = Split-Path $PSScriptRoot -Parent
if (-not $Tag) {
    & "$PSScriptRoot/release.ps1"
    exit $LASTEXITCODE
}
if (-not $ZipPath) {
    $ZipPath = Join-Path $root "dist\STS2_Skills-$Tag.zip"
}
$notesPath = Join-Path $root "RELEASE_NOTES_$Tag.md"
if (-not (Test-Path $ZipPath)) {
    throw "Zip not found: $ZipPath"
}
$notes = if (Test-Path $notesPath) { Get-Content $notesPath -Raw -Encoding UTF8 } else { "Release $Tag" }
$gh = "C:\Program Files\GitHub CLI\gh.exe"
if (-not (Test-Path $gh)) { $gh = "gh" }
& $gh release create $Tag $ZipPath --repo $Repo --title $Tag --notes $notes
Write-Host "Done: https://github.com/$Repo/releases/tag/$Tag"
