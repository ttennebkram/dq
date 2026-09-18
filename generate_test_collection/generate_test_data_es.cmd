@echo off
setlocal DisableDelayedExpansion
py.exe -3 "%~dp0generate_test_data_es.py" %*
exit /b %errorlevel%
