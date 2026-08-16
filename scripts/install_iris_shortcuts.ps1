# dist\IRIS.exe → 바탕화면 / 시작 메뉴 / 프로젝트 루트 바로가기
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$exe = Join-Path $root "dist\IRIS.exe"
if (-not (Test-Path $exe)) {
    throw "dist\IRIS.exe 없음 — 먼저 scripts\build_iris_exe.ps1 실행"
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
    $s.WorkingDirectory = Split-Path $exe -Parent
    $s.WindowStyle = 1
    $s.Description = "IRIS"
    $s.IconLocation = "$exe,0"
    $s.Save()
    Write-Host "Shortcut:" $LinkPath
}

New-IrisShortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "IRIS.lnk")
New-IrisShortcut (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\IRIS.lnk")
New-IrisShortcut (Join-Path $root "IRIS.lnk")
