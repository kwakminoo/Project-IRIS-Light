@echo off
cd /d "%~dp0"
REM dist\IRIS.exe = thin launcher → 항상 .venv 최신 소스
if exist "dist\IRIS.exe" (
  start "" "dist\IRIS.exe"
  exit /b 0
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m iris
) else if exist ".venv\Scripts\python.exe" (
  start "" ".venv\Scripts\python.exe" -m iris
) else (
  where pythonw >nul 2>&1 && (start "" pythonw -m iris) || (start "" python -m iris)
)
