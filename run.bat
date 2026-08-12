@echo off
cd /d "%~dp0"
REM 재빌드된 IRIS.exe 우선 (MCP는 venv python + ~/.iris-light/hermes-mcp entry 사용)
REM 문제 시: set IRIS_USE_VENV=1
if /I not "%IRIS_USE_VENV%"=="1" if exist "dist\IRIS.exe" (
  start "" "dist\IRIS.exe"
  exit /b 0
)
REM 콘솔 창 없이 GUI만 기동 (백엔드 Hermes/Ollama도 코드에서 창 숨김)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m iris
) else if exist ".venv\Scripts\python.exe" (
  start "" ".venv\Scripts\python.exe" -m iris
) else (
  where pythonw >nul 2>&1 && (start "" pythonw -m iris) || (start "" python -m iris)
)
