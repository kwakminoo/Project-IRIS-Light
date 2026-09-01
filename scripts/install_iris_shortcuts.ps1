# dist\IRIS.exe (thin launcher → 항상 최신 소스) → 바탕화면 / 시작메뉴 / 프로젝트 루트
# AppUserModelID 포함 — pythonw.exe 실행 시에도 작업표시줄 IRIS 아이콘
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$exe = Join-Path $root "dist\IRIS.exe"
$ico = Join-Path $root "iris\assets\iris_icon.ico"
if (-not (Test-Path $exe)) {
    throw "dist\IRIS.exe 없음 — 먼저 scripts\build_iris_exe.ps1 실행"
}
if (-not (Test-Path $ico)) {
    throw "iris\assets\iris_icon.ico 없음"
}

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}

& $py -m iris.assets.windows_taskbar install
if ($LASTEXITCODE -ne 0) {
    throw "shortcut install failed (exit $LASTEXITCODE)"
}
