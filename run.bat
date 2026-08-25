@echo off
cd /d "%~dp0"
REM ============================================================
REM IRIS 실행 — 기본은 소스(.venv). 로컬 수정이 즉시 반영됩니다.
REM
REM   패키지 EXE만 쓰려면:  set IRIS_USE_EXE=1
REM   EXE가 소스로 안 넘어가게: set IRIS_FORCE_FROZEN=1
REM ============================================================

if /I "%IRIS_USE_EXE%"=="1" (
  if exist "dist\IRIS.exe" (
    start "" "dist\IRIS.exe"
    exit /b 0
  )
  echo [IRIS] IRIS_USE_EXE=1 이지만 dist\IRIS.exe 가 없습니다.
)

if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m iris
  exit /b 0
)
if exist ".venv\Scripts\python.exe" (
  start "" ".venv\Scripts\python.exe" -m iris
  exit /b 0
)

REM venv 없으면 EXE 폴백 (새 빌드는 다시 .venv 소스로 hop)
if exist "dist\IRIS.exe" (
  start "" "dist\IRIS.exe"
  exit /b 0
)

where pythonw >nul 2>&1 && (start "" pythonw -m iris) || (start "" python -m iris)
