@echo off
cd /d "%~dp0"
REM 콘솔 창 없이 GUI만 기동 (백엔드 Hermes/Ollama도 코드에서 창 숨김)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m iris
) else if exist ".venv\Scripts\python.exe" (
  start "" ".venv\Scripts\python.exe" -m iris
) else (
  where pythonw >nul 2>&1 && (start "" pythonw -m iris) || (start "" python -m iris)
)
