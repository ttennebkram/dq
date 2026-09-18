@echo off
setlocal DisableDelayedExpansion
py.exe -3 "%~dp0generate_test_data_solr.py" %*
exit /b %errorlevel%
