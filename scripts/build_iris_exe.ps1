# IRIS.exe 빌드 — 아이콘 포함 one-file
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
