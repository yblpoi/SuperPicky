@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if /I "%~1"=="--help" goto :show_help
if /I "%~1"=="-h" goto :show_help

set "FIRST_ARG=%~1"

if "%~1"=="" goto :run_default
if "%FIRST_ARG:~0,2%"=="--" goto :run_passthrough
if not "%~3"=="" goto :show_positional_error

set "VERSION_ARG="
set "COPY_DIR_ARG="

if not "%~1"=="" set "VERSION_ARG=--version %~1"
if not "%~2"=="" set "COPY_DIR_ARG=--copy-dir %~2"

:run_default
"%PYTHON_EXE%" "%SCRIPT_DIR%build_release_win.py" --build-type cpu %VERSION_ARG% %COPY_DIR_ARG%
exit /b %ERRORLEVEL%

:run_passthrough
"%PYTHON_EXE%" "%SCRIPT_DIR%build_release_win.py" --build-type cpu %*
exit /b %ERRORLEVEL%

:show_help
echo SuperPicky Windows compatibility wrapper
echo.
echo Usage:
echo   %~nx0 [version] [copy_dir]
echo   %~nx0 [build_release_win.py options]
echo.
echo This wrapper forwards to build_release_win.py --build-type cpu.
echo If the first argument starts with --, all arguments are passed through directly.
exit /b 0

:show_positional_error
echo [ERROR] Positional compatibility mode only accepts [version] [copy_dir].
echo [ERROR] If you need extra options such as --debug or --help, use explicit option mode.
echo [ERROR] Example: build_release.bat --debug --help
exit /b 1