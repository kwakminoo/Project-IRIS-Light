@echo off
chcp 65001 >nul 2>&1
REM =====================================================
REM  IRIS 자동 설치 — 이 파일을 더블클릭하세요.
REM  PowerShell 실행 정책 때문에 setup.ps1 이 막히는 것을
REM  Bypass 로 우회해서 대신 실행해 줍니다.
REM =====================================================
setlocal
cd /d "%~dp0"

where powershell >nul 2>&1
if errorlevel 1 (
  echo.
  echo [오류] PowerShell 을 찾지 못했습니다. Windows 10/11 이 필요합니다.
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo 설치가 끝났습니다. run.bat 으로 IRIS 를 실행하세요.
) else (
  echo 설치 중 문제가 발생했습니다. 위 메시지를 확인하세요.
)
echo.
pause
exit /b %RC%
