@echo off
setlocal EnableExtensions

call "%~dp0build_release_cpu.bat" %*
if errorlevel 1 exit /b %ERRORLEVEL%

call "%~dp0build_release_lite_win.bat" %*
exit /b %ERRORLEVEL%