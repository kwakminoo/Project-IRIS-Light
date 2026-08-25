# IRIS.exe 빌드 — 아이콘 포함 one-file
# 참고: 일상 실행은 run.bat(.venv 소스)가 기본입니다.
# 이 EXE를 더블클릭해도 저장소에 .venv가 있으면 최신 소스로 hop 합니다.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

python -m pip install -q "pyinstaller>=6.0"
if (-not (Test-Path "iris\assets\iris_icon.ico")) {
  throw "iris/assets/iris_icon.ico 없음"
}

Write-Host "Building IRIS.exe ..."
python -m PyInstaller --noconfirm --clean IRIS.spec
if (-not (Test-Path "dist\IRIS.exe")) {
  throw "dist/IRIS.exe 생성 실패"
}

Write-Host "OK:" (Resolve-Path "dist\IRIS.exe")
& (Join-Path $PSScriptRoot "install_iris_shortcuts.ps1")
Write-Host "바로가기는 .venv 소스 우선입니다. EXE만 쓰려면 IRIS_FORCE_FROZEN=1"
