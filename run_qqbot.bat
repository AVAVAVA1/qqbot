@echo off
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0src\main.py"
) else (
  python "%~dp0src\main.py"
)
if errorlevel 1 pause
