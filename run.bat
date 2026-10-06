@echo off
setlocal
set "IRIS_ROOT=%~dp0"
cd /d "%IRIS_ROOT%"
if exist "%IRIS_ROOT%.venv\Scripts\pythonw.exe" (
  start "" "%IRIS_ROOT%.venv\Scripts\pythonw.exe" "%IRIS_ROOT%IRIS_launcher.py" %*
  exit /b 0
)
if exist "%IRIS_ROOT%.venv\Scripts\python.exe" (
  start "" "%IRIS_ROOT%.venv\Scripts\python.exe" "%IRIS_ROOT%IRIS_launcher.py" %*
  exit /b 0
)
REM dist\IRIS.exe = thin launcher → 항상 .venv 최신 소스
if exist "dist\IRIS.exe" (
  start "" "%IRIS_ROOT%dist\IRIS.exe" %*
  exit /b 0
)
where pythonw >nul 2>&1 && (start "" pythonw "%IRIS_ROOT%IRIS_launcher.py" %*) || (start "" python "%IRIS_ROOT%IRIS_launcher.py" %*)
