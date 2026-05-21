# STS2_Skills 一键安装（PowerShell）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$exe = Join-Path $PSScriptRoot "sts2skill.exe"
if (-not (Test-Path $exe)) {
  $exe = Join-Path $PSScriptRoot "install.exe"
}
if (Test-Path $exe) {
  & $exe @args
  exit $LASTEXITCODE
}
& python "$PSScriptRoot\scripts\sts2_setup_wizard.py" @args
exit $LASTEXITCODE
