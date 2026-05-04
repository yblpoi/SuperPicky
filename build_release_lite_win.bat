@echo off
setlocal EnableExtensions

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" "%~dp0build_release_win.py" --build-type lite %*
exit /b %ERRORLEVEL%
