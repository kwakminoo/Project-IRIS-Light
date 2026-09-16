# IRIS Windows Setup.exe 빌드 — 현재 워크스페이스 소스를 설치 패키지로 묶는다.
# 출력: dist\IRIS-Setup-0.1.0.exe
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$InstallerDir = Join-Path $Root "installer"
$Payload = Join-Path $InstallerDir "payload"
$Iss = Join-Path $InstallerDir "iris.iss"
$Icon = Join-Path $Root "iris\assets\iris_icon.ico"
$Exe = Join-Path $Root "dist\IRIS.exe"

function Find-ISCC {
    $paths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    if ($env:ProgramFiles) {
        $paths += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
    }
    $pf86 = [Environment]::GetFolderPath("ProgramFilesX86")
    if ($pf86) {
        $paths += Join-Path $pf86 "Inno Setup 6\ISCC.exe"
    }
    foreach ($p in $paths) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Invoke-Robocopy([string]$From, [string]$To, [string[]]$ExtraArgs) {
    if (-not (Test-Path $From)) { return }
    $null = New-Item -ItemType Directory -Force -Path $To
    $args = @($From, $To, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/XD", "__pycache__", ".pytest_cache", ".mypy_cache") + $ExtraArgs
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed ($LASTEXITCODE): $From -> $To"
    }
}

if (-not (Test-Path $Icon)) { throw "iris/assets/iris_icon.ico 없음" }
if (-not (Test-Path $Iss)) { throw "installer/iris.iss 없음" }

if (-not (Test-Path $Exe)) {
    Write-Host "dist\IRIS.exe 없음 — thin launcher 빌드"
    & (Join-Path $PSScriptRoot "build_iris_exe.ps1")
}

$Iscc = Find-ISCC
if (-not $Iscc) {
    throw "Inno Setup(ISCC.exe) 없음. winget install -e --id JRSoftware.InnoSetup"
}

Write-Host "Staging payload -> $Payload"
if (Test-Path $Payload) {
    Remove-Item -Recurse -Force $Payload
}
New-Item -ItemType Directory -Force -Path $Payload | Out-Null

$copyDirs = @("iris", "docs", "scripts", "services", "assets", "obsidian-vault")
foreach ($d in $copyDirs) {
    Invoke-Robocopy (Join-Path $Root $d) (Join-Path $Payload $d) @()
}

Invoke-Robocopy (Join-Path $Root "integrations") (Join-Path $Payload "integrations") @(
    "/XD", "node_modules", "lib", "plugins", ".theia"
)
Invoke-Robocopy (Join-Path $Root "android-emulator") (Join-Path $Payload "android-emulator") @(
    "/XD", "avd", "data"
)

$payloadDist = Join-Path $Payload "dist"
New-Item -ItemType Directory -Force -Path $payloadDist | Out-Null
Copy-Item -Force $Exe (Join-Path $payloadDist "IRIS.exe")

$rootFiles = @(
    "IRIS_launcher.py", "IRIS.spec", "LICENSE", "LICENSE.md", "README.md",
    "requirements.txt", "run.bat", "run.sh", "setup.bat", "setup.ps1", "setup.sh",
    ".env.example", ".gitignore"
)
foreach ($f in $rootFiles) {
    $src = Join-Path $Root $f
    if (Test-Path $src) {
        Copy-Item -Force $src (Join-Path $Payload $f)
    }
}

Write-Host "Compiling Setup.exe ..."
& $Iscc $Iss
if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }

$out = Join-Path $Root "dist\IRIS-Setup-0.1.0.exe"
if (-not (Test-Path $out)) { throw "출력 파일 없음: $out" }
$size = (Get-Item $out).Length
Write-Host "OK:" (Resolve-Path $out) "($([math]::Round($size/1MB, 1)) MB)"
