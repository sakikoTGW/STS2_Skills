# STS2_Skills 一键安装（PowerShell）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& python "$PSScriptRoot\scripts\sts2_setup_wizard.py" @args
exit $LASTEXITCODE
