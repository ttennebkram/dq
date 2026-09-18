@echo off
setlocal DisableDelayedExpansion
py.exe -3 "%~dp0submit_to_es.py" %*
exit /b %errorlevel%
