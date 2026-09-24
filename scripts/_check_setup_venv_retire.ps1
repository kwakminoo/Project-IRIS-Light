# setup.ps1 Remove-TreeSafe / 잠금 rename 계약 자검
# 실행: powershell -ExecutionPolicy Bypass -File scripts\_check_setup_venv_retire.ps1
$ErrorActionPreference = "Stop"

function Stop-IrisVenvHolders {
    param([string]$Tree, [string]$AppRoot = $null)
    if (-not $Tree) { return }
    try { $norm = [IO.Path]::GetFullPath($Tree).TrimEnd('\') } catch { return }
    $me = $PID
    foreach ($proc in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
        if (-not $proc -or $proc.ProcessId -eq $me) { continue }
        $exe = [string]$proc.ExecutablePath
        $cmd = [string]$proc.CommandLine
        $hit = $false
        if ($exe -and $exe.StartsWith($norm, [StringComparison]::OrdinalIgnoreCase)) { $hit = $true }
        if (-not $hit -and $cmd -and $cmd.IndexOf($norm, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $hit = $true
        }
        if (-not $hit) { continue }
        try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue } catch { }
    }
    Start-Sleep -Milliseconds 200
}

function Remove-TreeSafe {
    param([string]$Path, [string]$Label = ".venv")
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $true }
    Stop-IrisVenvHolders -Tree $Path
    for ($i = 1; $i -le 3; $i++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            if (-not (Test-Path -LiteralPath $Path)) { return $true }
        } catch {
            Stop-IrisVenvHolders -Tree $Path
            Start-Sleep -Milliseconds (200 * $i)
        }
    }
    $parent = Split-Path -Parent $Path
    $leaf = Split-Path -Leaf $Path
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $trashName = "$leaf.trash-$stamp"
    $trash = Join-Path $parent $trashName
    $moved = $false
    try {
        [System.IO.Directory]::Move($Path, $trash)
        $moved = $true
    } catch {
        try {
            Rename-Item -LiteralPath $Path -NewName $trashName -ErrorAction Stop
            $moved = $true
        } catch { }
    }
    if (-not $moved -and (Test-Path -LiteralPath $Path)) {
        foreach ($rel in @("Scripts\python.exe", "Scripts\pythonw.exe")) {
            $locked = Join-Path $Path $rel
            if (-not (Test-Path -LiteralPath $locked)) { continue }
            $q = "$locked.quarantine-$stamp"
            try { [System.IO.File]::Move($locked, $q) } catch {
                try {
                    Rename-Item -LiteralPath $locked -NewName ((Split-Path $rel -Leaf) + ".quarantine-$stamp") -ErrorAction SilentlyContinue
                } catch { }
            }
        }
        Start-Sleep -Milliseconds 200
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            if (-not (Test-Path -LiteralPath $Path)) { return $true }
        } catch { }
        try {
            [System.IO.Directory]::Move($Path, $trash)
            $moved = $true
        } catch { return $false }
    }
    if (-not $moved) { return -not (Test-Path -LiteralPath $Path) }
    Remove-Item -LiteralPath $trash -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath $parent -Filter "$leaf.trash-*" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    Get-ChildItem -LiteralPath $parent -Recurse -Filter "*.quarantine-*" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }
    return -not (Test-Path -LiteralPath $Path)
}

$root = Join-Path $env:TEMP ("iris-setup-retire-" + [guid]::NewGuid().ToString("n").Substring(0, 8))
New-Item -ItemType Directory -Force -Path (Join-Path $root "Scripts") | Out-Null
Set-Content -LiteralPath (Join-Path $root "Scripts\python.exe") -Value ("x" * 2048) -Encoding ascii
Set-Content -LiteralPath (Join-Path $root "pyvenv.cfg") -Value "home = x" -Encoding ascii

if (-not (Remove-TreeSafe -Path $root -Label "t1")) { throw "unlocked remove failed" }
if (Test-Path -LiteralPath $root) { throw "unlocked path still exists" }
Write-Host "OK unlocked Remove-TreeSafe"

# 프로세스 잠금 시뮬레이션: 자식이 트리 경로를 CommandLine 에 들고 Sleep
$root2 = Join-Path $env:TEMP ("iris-setup-retire-" + [guid]::NewGuid().ToString("n").Substring(0, 8))
$scripts = Join-Path $root2 "Scripts"
New-Item -ItemType Directory -Force -Path $scripts | Out-Null
$py2 = Join-Path $scripts "python.exe"
Set-Content -LiteralPath $py2 -Value ("x" * 2048) -Encoding ascii
Set-Content -LiteralPath (Join-Path $root2 "pyvenv.cfg") -Value "home = x" -Encoding ascii

$holder = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -PassThru -ArgumentList @(
    "-NoProfile", "-Command",
    "Start-Sleep -Seconds 60; Get-Content -LiteralPath '$py2' | Out-Null"
)
try {
    Start-Sleep -Milliseconds 500
    $ok = Remove-TreeSafe -Path $root2 -Label "t2"
    if (-not $ok) { throw "process-holder retire failed" }
    if (Test-Path -LiteralPath $root2) { throw "process-holder original path still present" }
    Write-Host "OK process CommandLine holder → retire"
} finally {
    if ($holder -and -not $holder.HasExited) {
        Stop-Process -Id $holder.Id -Force -ErrorAction SilentlyContinue
    }
    Get-ChildItem -LiteralPath (Split-Path $root2 -Parent) -Directory -Filter "iris-setup-retire-*" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
}

# AV 유사: 배타 핸들을 재시도 도중에 풀어 주면 삭제 성공
$root3 = Join-Path $env:TEMP ("iris-setup-retire-" + [guid]::NewGuid().ToString("n").Substring(0, 8))
New-Item -ItemType Directory -Force -Path (Join-Path $root3 "Scripts") | Out-Null
$py3 = Join-Path $root3 "Scripts\python.exe"
Set-Content -LiteralPath $py3 -Value ("x" * 2048) -Encoding ascii
$fs = [System.IO.File]::Open($py3, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::None)
try {
    $ps = [PowerShell]::Create()
    [void]$ps.AddScript('param($h) Start-Sleep -Milliseconds 700; $h.Dispose()').AddArgument($fs)
    $async = $ps.BeginInvoke()
    $ok3 = Remove-TreeSafe -Path $root3 -Label "t3"
    [void]$ps.EndInvoke($async)
    $ps.Dispose()
    if (-not $ok3) { throw "brief-lock retry retire failed" }
    if (Test-Path -LiteralPath $root3) { throw "brief-lock original path still present" }
    Write-Host "OK brief exclusive lock → retry remove"
} finally {
    try { $fs.Dispose() } catch { }
    Get-ChildItem -LiteralPath (Split-Path $root3 -Parent) -Directory -Filter "iris-setup-retire-*" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
}

Write-Host "ALL CHECKS PASSED"
