@echo off
setlocal EnableExtensions

call "%~dp0build_release.bat" "%~1" "output"
exit /b %ERRORLEVEL%
