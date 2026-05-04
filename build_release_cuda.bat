@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

set "VERSION_ARG="
if not "%~1"=="" set "VERSION_ARG=--version %~1"

"%PYTHON_EXE%" "%SCRIPT_DIR%build_release_win.py" --build-type cuda %VERSION_ARG% --copy-dir output\win64_cuda
exit /b %ERRORLEVEL%
