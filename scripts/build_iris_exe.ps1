# IRIS.exe thin launcher 빌드 — 투명 아이콘 포함, 실행 시 항상 최신 소스
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

python -m pip install -q "pyinstaller>=6.0"
if (-not (Test-Path "iris\assets\iris_icon.ico")) {
  throw "iris/assets/iris_icon.ico 없음"
}

# 아이콘 검정 배경 → 투명 (이미 투명해도 재적용 가능)
python (Join-Path $PSScriptRoot "_make_icon_transparent.py")

Write-Host "Building IRIS.exe (thin launcher) ..."
python -m PyInstaller --noconfirm --clean IRIS.spec
if (-not (Test-Path "dist\IRIS.exe")) {
  throw "dist/IRIS.exe 생성 실패"
}

$size = (Get-Item "dist\IRIS.exe").Length
Write-Host "OK:" (Resolve-Path "dist\IRIS.exe") "($([math]::Round($size/1KB)) KB)"
& (Join-Path $PSScriptRoot "install_iris_shortcuts.ps1")
