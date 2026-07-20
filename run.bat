@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m iris
) else (
  python -m iris
)
if errorlevel 1 pause
