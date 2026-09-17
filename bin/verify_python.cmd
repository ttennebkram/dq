@echo off
setlocal DisableDelayedExpansion
if not "%~1"=="" (
  echo Usage: verify_python.cmd ^(no arguments^)
  exit /b 2
)
where py.exe >nul 2>nul
if errorlevel 1 (
  echo FAIL: py.exe was not found. Install Python 3 and its Windows launcher. 1>&2
  exit /b 1
)
py.exe -3 --version
if errorlevel 1 exit /b %errorlevel%
py.exe -3 "%~dp0dq" --version
if errorlevel 1 exit /b %errorlevel%
echo PASS: Python 3 and the DQ CLI are available.
exit /b 0
