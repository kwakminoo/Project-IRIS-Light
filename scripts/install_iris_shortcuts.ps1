# IRIS 바로가기 — 소스(.venv) 우선. 로컬 수정이 즉시 반영됩니다.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$icon = Join-Path $root "iris\assets\iris_icon.ico"
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$python = Join-Path $root ".venv\Scripts\python.exe"
$runBat = Join-Path $root "run.bat"
$exe = Join-Path $root "dist\IRIS.exe"

function New-IrisShortcut {
    param(
        [string]$LinkPath,
        [string]$TargetPath,
        [string]$Arguments = "",
        [string]$WorkingDirectory,
        [string]$IconLocation = ""
    )
    $shell = New-Object -ComObject WScript.Shell
    $dir = Split-Path $LinkPath -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $s = $shell.CreateShortcut($LinkPath)
    $s.TargetPath = $TargetPath
    $s.Arguments = $Arguments
    $s.WorkingDirectory = $WorkingDirectory
    $s.WindowStyle = 1
    $s.Description = "IRIS (source)"
    if ($IconLocation -and (Test-Path $IconLocation)) {
        $s.IconLocation = "$IconLocation,0"
    }
    $s.Save()
    Write-Host "Shortcut:" $LinkPath "->" $TargetPath $Arguments
}

$work = $root
if (Test-Path $pythonw) {
    $target = $pythonw
    $args = "-m iris"
    $ico = if (Test-Path $icon) { $icon } else { $pythonw }
} elseif (Test-Path $python) {
    $target = $python
    $args = "-m iris"
    $ico = if (Test-Path $icon) { $icon } else { $python }
} elseif (Test-Path $runBat) {
    $target = $runBat
    $args = ""
    $ico = if (Test-Path $icon) { $icon } elseif (Test-Path $exe) { $exe } else { $runBat }
} elseif (Test-Path $exe) {
    Write-Host "경고: .venv 없음 — dist\IRIS.exe 사용 (소스 hop은 새 EXE 빌드 후)"
    $target = $exe
    $args = ""
    $work = Split-Path $exe -Parent
    $ico = $exe
} else {
    throw "실행 대상 없음 — .venv 생성 또는 scripts\build_iris_exe.ps1"
}

New-IrisShortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "IRIS.lnk") $target $args $work $ico
New-IrisShortcut (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\IRIS.lnk") $target $args $work $ico
New-IrisShortcut (Join-Path $root "IRIS.lnk") $target $args $work $ico
