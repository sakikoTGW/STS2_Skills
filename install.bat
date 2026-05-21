@echo off
chcp 65001 >nul
cd /d "%~dp0"
title STS2_Skills 安装向导
echo.
echo  ========================================
echo   STS2_Skills 一键安装
echo  ========================================
echo.
where python >nul 2>&1
if errorlevel 1 (
  echo 未找到 python，请先安装 Python 3.11+ 并加入 PATH。
  pause
  exit /b 1
)
python "%~dp0scripts\sts2_setup_wizard.py" %*
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" (
  echo 安装未完全成功，错误码 %ERR%
) else (
  echo 安装流程已结束。
)
pause
exit /b %ERR%
