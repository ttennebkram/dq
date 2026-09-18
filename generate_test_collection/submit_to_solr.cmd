@echo off
setlocal DisableDelayedExpansion
py.exe -3 "%~dp0submit_to_solr.py" %*
exit /b %errorlevel%
