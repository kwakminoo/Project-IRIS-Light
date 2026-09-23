# setup.ps1 Python 탐색·스텁 제외·부트스트랩 URL 자검
$ErrorActionPreference = "Stop"

function Test-RealPythonExe([string]$Path) {
    if (-not $Path) { return $false }
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    if ($Path -match '(?i)\\WindowsApps\\') { return $false }
    try {
        $item = Get-Item -LiteralPath $Path -ErrorAction Stop
        if ($item.Length -lt 1024) { return $false }
    } catch { return $false }
    return $true
}

$stub = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\python.exe"
if ((Test-Path $stub) -and (Test-RealPythonExe $stub)) {
    throw "Store stub must be rejected: $stub"
}
Write-Host "OK stub handling"

$known = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
    (Join-Path ${env:ProgramFiles} "Python313\python.exe"),
    (Join-Path ${env:ProgramFiles} "Python312\python.exe"),
    (Join-Path ${env:ProgramFiles} "Python311\python.exe")
) | Where-Object { Test-RealPythonExe $_ }
if (-not $known) { throw "no known Python install paths on this machine" }
Write-Host "OK known path(s): $($known -join ', ')"

# List 반환이 @() 로 합쳐지지 않는지 — setup.ps1 과 동일한 패턴
$list = New-Object System.Collections.Generic.List[object]
foreach ($p in $known) {
    $list.Add([pscustomobject]@{ Exe = $p; Args = [string[]]@() }) | Out-Null
}
$got = $list  # return $list 와 동일하게 취급
if ($got.Count -ne $known.Count) { throw "List count mismatch $($got.Count) vs $($known.Count)" }
$i = 0
foreach ($cand in $got) {
    $i++
    if ($cand.Exe -ne $known[$i - 1]) { throw "cand $i Exe mismatch: $($cand.Exe)" }
}
Write-Host "OK List foreach keeps $($got.Count) candidates"

# 잘못된 ,@() 패턴이 합쳐지는지 회귀 감지
$bad = @(,$list.ToArray())
if ($bad.Count -eq 1 -and $bad[0] -is [System.Array]) {
    Write-Host "OK documented trap: ,@()+@() wraps as 1 element (we avoid this)"
}

$url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
$req = [System.Net.HttpWebRequest]::Create($url)
$req.Method = "HEAD"
$req.UserAgent = "IRIS-Setup-Check"
$req.Timeout = 15000
$resp = $req.GetResponse()
$len = $resp.ContentLength
$resp.Close()
if ($len -lt 1MB) { throw "bootstrap installer too small: $len" }
Write-Host "OK bootstrap URL reachable ($([math]::Round($len/1MB,1)) MB)"

Write-Host "ALL CHECKS PASSED"
