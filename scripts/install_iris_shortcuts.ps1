# dist\IRIS.exe (thin launcher → 항상 최신 소스) → 바탕화면 / 시작메뉴 / 프로젝트 루트
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

function New-IrisShortcut {
    param([string]$LinkPath)
    $shell = New-Object -ComObject WScript.Shell
    $dir = Split-Path $LinkPath -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $s = $shell.CreateShortcut($LinkPath)
    $s.TargetPath = $exe
    $s.Arguments = ""
    $s.WorkingDirectory = Split-Path $exe -Parent
    $s.WindowStyle = 1
    $s.Description = "IRIS (latest via launcher)"
    # 투명 아이콘 보장 — exe 내장 + ico 직접 지정
    $s.IconLocation = "$ico,0"
    $s.Save()
    Write-Host "Shortcut:" $LinkPath "->" $exe
}

New-IrisShortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "IRIS.lnk")
New-IrisShortcut (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\IRIS.lnk")
New-IrisShortcut (Join-Path $root "IRIS.lnk")
