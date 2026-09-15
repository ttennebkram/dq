@echo off
setlocal DisableDelayedExpansion
rem Use the Windows Python launcher to select Python 3.
py.exe -3 "%~dp0dq.py" %*
exit /b %errorlevel%
