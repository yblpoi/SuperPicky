@echo off
setlocal EnableExtensions

set "VERSION_INPUT=%~1"
if "%VERSION_INPUT%"=="" (
    set "VERSION_ARG=Win64_CUDA"
) else (
    set "VERSION_ARG=%VERSION_INPUT%Win64_CUDA"
)

call "%~dp0.venv-cuda\Scripts\activate.bat"
if errorlevel 1 exit /b 1

set "OUT_DIST_DIR=dist_cuda"
call "%~dp0build_release.bat" "%VERSION_ARG%" "output"
set "RET=%ERRORLEVEL%"

call "%~dp0.venv-cuda\Scripts\deactivate.bat" >nul 2>&1
exit /b %RET%
