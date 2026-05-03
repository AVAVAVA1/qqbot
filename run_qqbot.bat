@echo off
cd /d "%~dp0"
set "PYEXE="
if exist "%~dp0.venv\Scripts\python.exe" set "PYEXE=%~dp0.venv\Scripts\python.exe"
if not defined PYEXE if exist "%~dp0venv\Scripts\python.exe" set "PYEXE=%~dp0venv\Scripts\python.exe"
if not defined PYEXE if exist "%~dp0env\Scripts\python.exe" set "PYEXE=%~dp0env\Scripts\python.exe"
if defined PYEXE (
  "%PYEXE%" "%~dp0src\main.py"
) else (
  python "%~dp0src\main.py"
)
if errorlevel 1 pause
