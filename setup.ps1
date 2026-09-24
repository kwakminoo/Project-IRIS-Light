<#
.SYNOPSIS
    IRIS 자동 설치 · 환경 구성 스크립트 (Windows)

.DESCRIPTION
    Python 확인 → 가상환경 생성 → 의존성 설치 → .env 준비 → 설치 검증까지
    한 번에 수행합니다. 초보자는 setup.bat 을 더블클릭하면 이 스크립트가 실행됩니다.

.PARAMETER Voice
    선택 음성 런타임(.venv-voice)까지 같이 설치합니다. 시간이 오래 걸립니다.

.PARAMETER Recreate
    기존 .venv 를 지우고 새로 만듭니다. 설치가 꼬였을 때 사용하세요.

.PARAMETER Run
    설치가 끝나면 바로 IRIS 를 실행합니다.

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -Run
    .\setup.ps1 -Voice -Recreate
#>
param(
    [switch]$Voice,
    [switch]$Recreate,
    [switch]$Run
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$VenvPath = Join-Path $Root ".venv"
$LogFile = Join-Path $Root "setup-log.txt"
$PipLog = Join-Path $Root "setup-log-pip.txt"
$FailReasonFile = Join-Path $Root "setup-fail-reason.txt"
$MinMajor = 3
$MinMinor = 11
$MaxMinorExclusive = 14
# Setup.exe 가 Python 없이 깔리는 PC 대비 — 공식 설치 파일을 받아 조용히 깐다.
$BootstrapPyVer = "3.12.10"
$BootstrapPyUrl = "https://www.python.org/ftp/python/$BootstrapPyVer/python-$BootstrapPyVer-amd64.exe"

# ---------------------------------------------------------------- 출력 헬퍼
$script:StepNo = 0
function Write-Step([string]$Message) {
    $script:StepNo++
    Write-Host ""
    Write-Host "[$script:StepNo/6] $Message" -ForegroundColor Cyan
}
function Write-Ok([string]$Message)   { Write-Host "  OK   $Message" -ForegroundColor Green }
function Write-Info([string]$Message) { Write-Host "  ...  $Message" -ForegroundColor DarkGray }
function Write-Warn([string]$Message) { Write-Host "  경고 $Message" -ForegroundColor Yellow }

$script:Transcribing = $false
function Stop-Log {
    if ($script:Transcribing) {
        try { Stop-Transcript | Out-Null } catch { }
        $script:Transcribing = $false
    }
}

function Fail([string]$Message, [string[]]$Hints) {
    Write-Host ""
    Write-Host "설치 실패: $Message" -ForegroundColor Red
    if ($Hints) {
        Write-Host ""
        Write-Host "해결 방법:" -ForegroundColor Yellow
        foreach ($h in $Hints) { Write-Host "  - $h" }
    }
    Write-Host ""
    Write-Host "전체 기록: $LogFile" -ForegroundColor DarkGray
    if (Test-Path $PipLog) { Write-Host "설치 상세: $PipLog" -ForegroundColor DarkGray }
    Write-Host ""
    # Inno LoadStringsFromFile 은 UTF-8 BOM + ASCII FAIL: 이 가장 안전하다
    try {
        $oneLine = ($Message -replace '[\r\n]+', ' ').Trim()
        if ($oneLine.Length -gt 300) { $oneLine = $oneLine.Substring(0, 300) + "..." }
        $payload = "FAIL: $oneLine`r`n설치 실패: $oneLine`r`n"
        [System.IO.File]::WriteAllText(
            $FailReasonFile,
            $payload,
            (New-Object System.Text.UTF8Encoding $true)
        )
    } catch { }
    Stop-Log
    exit 1
}

# 숨김 설치에서 예외가 나도 원인 파일을 남긴다 (빈 Setup 대화상자 방지)
trap {
    try {
        $m = $_.Exception.Message
        if (-not $m) { $m = "$_" }
        Fail "스크립트 오류: $m" @(
            "설치 폴더에서 setup.bat 을 다시 실행하세요",
            ".\setup.ps1 -Recreate"
        )
    } catch {
        exit 1
    }
}


# Inno/숨김 창에서도 방금 깐 Python 이 보이도록 Machine+User PATH 를 다시 읽는다.
function Refresh-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($machine -or $user) { $env:Path = "$user;$machine" }
}

# Microsoft Store 실행 별칭(0바이트) · WindowsApps 스텁은 제외.
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

function Resolve-CommandExe([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    $src = $cmd.Source
    if (-not $src) { return $null }
    if ($Name -match '^(py|python|python3)$' -and -not (Test-RealPythonExe $src)) {
        # py.exe 런처(C:\Windows\py.exe)는 작을 수 있어도 허용
        if ($Name -eq "py" -and (Test-Path -LiteralPath $src)) { return $src }
        return $null
    }
    return $src
}

# 창을 닫으면 화면 기록은 사라진다. 중간에 끊겨도 원인이 남도록 파일로 받아 둔다.
# 단, PowerShell 5.1 트랜스크립트는 pip 같은 네이티브 출력을 담지 못한다 —
# 그건 pip 자체 --log 로 $PipLog 에 따로 받는다.
Remove-Item $PipLog -ErrorAction SilentlyContinue
Remove-Item $FailReasonFile -ErrorAction SilentlyContinue
try {
    Start-Transcript -Path $LogFile -Force | Out-Null
    $script:Transcribing = $true
} catch {
    Write-Host "  경고 로그 파일을 열지 못했습니다: $LogFile" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host "  IRIS 자동 설치" -ForegroundColor Magenta
Write-Host "  경로: $Root" -ForegroundColor DarkGray
Write-Host "===============================================" -ForegroundColor Magenta

# ------------------------------------------------------- 1. Python 찾기
Write-Step "Python 3.$MinMinor–3.13 확인"
Refresh-ProcessPath

function Get-PythonCandidates {
    # ponytail: return ,$array + @() 조합은 후보 Object[] 를 한 원소로 감싸
    # $cand.Exe 가 모든 경로를 공백으로 이어 붙인다. List 를 그대로 돌려 for-each 한다.
    $list = New-Object System.Collections.Generic.List[object]
    $seen = @{}

    $queue = New-Object System.Collections.Generic.List[object]
    $py = Resolve-CommandExe "py"
    if ($py) {
        foreach ($flag in @("-3.13", "-3.12", "-3.11", "-3")) {
            $queue.Add([pscustomobject]@{ Exe = $py; Args = [string[]]@($flag) }) | Out-Null
        }
    }
    foreach ($p in @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        (Join-Path ${env:ProgramFiles} "Python313\python.exe"),
        (Join-Path ${env:ProgramFiles} "Python312\python.exe"),
        (Join-Path ${env:ProgramFiles} "Python311\python.exe")
    )) {
        if (Test-RealPythonExe $p) {
            $queue.Add([pscustomobject]@{ Exe = $p; Args = [string[]]@() }) | Out-Null
        }
    }
    foreach ($name in @("python", "python3")) {
        $exe = Resolve-CommandExe $name
        if ($exe) {
            $queue.Add([pscustomobject]@{ Exe = $exe; Args = [string[]]@() }) | Out-Null
        }
    }

    foreach ($e in $queue) {
        $key = ($e.Exe + "|" + ($e.Args -join " ")).ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        $list.Add($e) | Out-Null
    }
    return $list
}

function Find-CompatiblePython {
    $cands = Get-PythonCandidates
    foreach ($cand in $cands) {
        $exe = [string]$cand.Exe
        $argv = @($cand.Args)
        if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { continue }
        try {
            if ($argv.Count -gt 0) {
                $raw = & $exe @argv -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
            } else {
                $raw = & $exe -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
            }
        } catch { continue }
        if ($LASTEXITCODE -ne 0) { continue }
        if (-not $raw) { continue }
        $v = ($raw | Select-Object -First 1).Trim()
        $parts = $v.Split(".")
        if ($parts.Count -lt 2) { continue }
        $maj = [int]$parts[0]; $min = [int]$parts[1]
        if ($maj -eq $MinMajor -and $min -ge $MinMinor -and $min -lt $MaxMinorExclusive) {
            return @{ Exe = $exe; Args = $argv; Version = $v }
        }
    }
    return $null
}

function Find-WingetExe {
    foreach ($c in @(
        (Resolve-CommandExe "winget"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\winget.exe"),
        (Join-Path ${env:ProgramFiles} "WindowsApps\Microsoft.DesktopAppInstaller_*\winget.exe")
    )) {
        if (-not $c) { continue }
        if ($c -match '\*') {
            $hit = Get-Item $c -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit -and $hit.Length -gt 1024) { return $hit.FullName }
            continue
        }
        if ((Test-Path -LiteralPath $c) -and ((Get-Item -LiteralPath $c).Length -gt 1024)) {
            return $c
        }
    }
    return $null
}

function Install-PythonBootstrap {
    Write-Info "호환 Python 없음 — $BootstrapPyVer 자동 설치 시도 (인터넷 필요)"

    $winget = Find-WingetExe
    if ($winget) {
        Write-Info "winget 으로 Python 3.12 설치..."
        & $winget install -e --id Python.Python.3.12 --accept-package-agreements `
            --accept-source-agreements --disable-interactivity --scope user 2>&1 | Out-Null
        Refresh-ProcessPath
        $found = Find-CompatiblePython
        if ($found) { return $found }
        Write-Warn "winget 설치 후에도 Python 을 찾지 못함 — 공식 설치 파일로 재시도"
    }

    $tmp = Join-Path $env:TEMP "iris-python-$BootstrapPyVer-amd64.exe"
    try {
        Write-Info "다운로드: $BootstrapPyUrl"
        # BITS/Invoke-WebRequest 둘 다 깨지는 PC 대비 — .NET 으로 받는다
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $wc = New-Object System.Net.WebClient
        $wc.Headers.Add("User-Agent", "IRIS-Setup")
        $wc.DownloadFile($BootstrapPyUrl, $tmp)
    } catch {
        Write-Warn "다운로드 실패: $($_.Exception.Message)"
        return $null
    }
    if (-not (Test-Path $tmp) -or (Get-Item $tmp).Length -lt 1MB) {
        Write-Warn "다운로드 파일이 비정상입니다"
        return $null
    }

    Write-Info "조용히 설치 중 (현재 사용자 · PATH 등록)..."
    $installerArgs = @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_test=0",
        "Include_doc=0",
        "Include_dev=0",
        "Include_launcher=1",
        "AssociateFiles=0",
        "Shortcuts=0"
    )
    $p = Start-Process -FilePath $tmp -ArgumentList $installerArgs -Wait -PassThru
    Refresh-ProcessPath
    # 설치 직후 레지스트리/폴더가 늦게 보일 수 있어 잠깐 재탐색
    for ($i = 0; $i -lt 8; $i++) {
        $found = Find-CompatiblePython
        if ($found) { return $found }
        Start-Sleep -Seconds 1
        Refresh-ProcessPath
    }
    if ($p.ExitCode -ne 0) {
        Write-Warn "Python 설치 프로그램 exit code $($p.ExitCode)"
    }
    return $null
}

$hit = Find-CompatiblePython
if (-not $hit) {
    $hit = Install-PythonBootstrap
}

if (-not $hit) {
    Fail "Hermes 호환 Python 3.$MinMinor–3.13을 찾지 못했고 자동 설치에도 실패했습니다." @(
        "인터넷 연결을 확인하세요",
        "https://www.python.org/downloads/release/python-31210/ 에서 Windows installer (64-bit) 설치",
        "설치 화면에서 [Add python.exe to PATH] 체크 필수",
        "설치 후 이 창을 닫고 setup.bat 을 다시 실행하세요"
    )
}

$PyExe = $hit.Exe
$PyArgs = $hit.Args
$PyVersion = $hit.Version
Write-Ok "Python $PyVersion ($PyExe $($PyArgs -join ' '))"

# ------------------------------------------------------- 2. 가상환경
Write-Step "가상환경(.venv) 준비"

function Test-VenvUsable([string]$Path) {
    $cfg = Join-Path $Path "pyvenv.cfg"
    $py = Join-Path $Path "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $cfg)) { return $false }
    if (-not (Test-Path -LiteralPath $py)) { return $false }
    return $true
}

if ($Recreate -and (Test-Path $VenvPath)) {
    Write-Info "-Recreate: 기존 .venv 삭제"
    Remove-Item -Recurse -Force $VenvPath
}

$VenvPy = Join-Path $VenvPath "Scripts\python.exe"
$VenvCfg = Join-Path $VenvPath "pyvenv.cfg"

# Scripts만 남고 pyvenv.cfg 가 없으면 python 이 "No pyvenv.cfg" 로 즉사한다 → 자동 재생성
if ((Test-Path $VenvPath) -and -not (Test-VenvUsable $VenvPath)) {
    Write-Warn "깨진 .venv 감지 (pyvenv.cfg 없음) — 삭제 후 다시 만듭니다"
    Remove-Item -Recurse -Force $VenvPath -ErrorAction SilentlyContinue
}

if (Test-VenvUsable $VenvPath) {
    $VenvVersion = & $VenvPy -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if (-not $VenvVersion -or $VenvVersion -notmatch '^3\.(11|12|13)$') {
        Fail "기존 .venv의 Python($VenvVersion)은 Hermes와 호환되지 않습니다." @(
            ".\setup.ps1 -Recreate 로 3.11–3.13 가상환경을 새로 만드세요"
        )
    }
    Write-Ok ".venv 이미 존재 — 재사용 (새로 만들려면 -Recreate)"
} else {
    Write-Info "생성 중..."
    & $PyExe @PyArgs -m venv $VenvPath
    if (-not (Test-VenvUsable $VenvPath)) {
        Fail "가상환경 생성에 실패했습니다." @(
            "$PyExe $($PyArgs -join ' ') -m ensurepip 실행 후 재시도",
            "Microsoft Store 버전 Python은 문제가 생길 수 있습니다. python.org 배포판을 권장합니다"
        )
    }
    Write-Ok "생성 완료: $VenvPath"
}

# ------------------------------------------------------- 3. pip 업그레이드
Write-Step "pip 업그레이드"

# PATH 에 깨진 정션/마운트(WinError 448)가 있으면 pip 이 설치 중 죽는다.
# (예: 일부 클라우드 PC · Cua driver bin 등) — 0.1.7 검증된 최소 스크럽만 유지
function Set-PipSafePath {
    $keep = New-Object System.Collections.Generic.List[string]
    foreach ($part in @(
        (Join-Path $VenvPath "Scripts"),
        "$env:SystemRoot\System32",
        "$env:SystemRoot",
        "$env:SystemRoot\System32\Wbem"
    )) {
        if ($part -and (Test-Path -LiteralPath $part)) { $keep.Add($part) | Out-Null }
    }
    foreach ($part in ($env:Path -split ';')) {
        if ([string]::IsNullOrWhiteSpace($part)) { continue }
        if ($part -match '(?i)\\Cua\\|\\cua-driver\\') { continue }
        try {
            if (-not (Test-Path -LiteralPath $part)) { continue }
            $null = Get-Item -LiteralPath $part -ErrorAction Stop
            if (-not $keep.Contains($part)) { $keep.Add($part) | Out-Null }
        } catch {
            Write-Warn "PATH에서 제외 (접근 불가): $part"
        }
    }
    $env:Path = ($keep -join ';')
    $env:PYTHONNOUSERSITE = "1"
}

function Get-PipLogErrorTail {
    if (-not (Test-Path -LiteralPath $PipLog)) { return "" }
    try {
        $lines = Get-Content -LiteralPath $PipLog -Tail 120 -ErrorAction Stop
    } catch { return "" }
    $hit = $lines | Where-Object { $_ -match 'ERROR:|WinError\s*\d+|No matching distribution|Could not find|SSLError|ProxyError' }
    if (-not $hit) { $hit = $lines | Select-Object -Last 5 }
    $err = ($hit | Select-Object -Last 3) -join " | "
    if ($err.Length -gt 280) { $err = $err.Substring($err.Length - 280) }
    return $err
}

function Ensure-VenvPip {
    & $VenvPy -m pip --version 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return $true }
    Write-Warn "venv pip 없음 — ensurepip 실행"
    & $VenvPy -m ensurepip --upgrade 2>$null | Out-Null
    & $VenvPy -m pip --version 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Invoke-PipInstallRequirements {
    param([string[]]$ExtraArgs = @())
    Set-PipSafePath
    if (-not (Ensure-VenvPip)) { return 1 }
    & $VenvPy -m pip install --upgrade pip --disable-pip-version-check --no-input -q
    & $VenvPy -m pip install -r $Requirements --log $PipLog `
        --disable-pip-version-check --no-input --retries 8 --timeout 120 `
        @ExtraArgs
    return $LASTEXITCODE
}

Set-PipSafePath
if (-not (Ensure-VenvPip)) {
    Fail "가상환경에 pip 를 설치하지 못했습니다." @(
        ".\setup.ps1 -Recreate 로 다시 시도하세요",
        "python.org 에서 Python 3.12 설치 시 pip 옵션을 켜세요"
    )
}

& $VenvPy -m pip install --upgrade pip --disable-pip-version-check --no-input -q
if ($LASTEXITCODE -ne 0) { Write-Warn "pip 업그레이드 실패 — 기존 pip으로 계속합니다" } else { Write-Ok "pip 최신" }

# ------------------------------------------------------- 4. 의존성 설치
Write-Step "의존성 설치 (requirements.txt) — 수 분 걸릴 수 있습니다"

$Requirements = Join-Path $Root "requirements.txt"
if (-not (Test-Path -LiteralPath $Requirements)) {
    Fail "requirements.txt 가 없습니다: $Requirements" @("Setup.exe 를 다시 받아 설치하세요")
}

$pipRc = 1
$pipAttempts = @(
    @{ Extra = @(); Label = "기본" },
    @{ Extra = @(); Label = "재시도" },
    @{
        Extra = @(
            "--trusted-host", "pypi.org",
            "--trusted-host", "files.pythonhosted.org",
            "--trusted-host", "pypi.python.org"
        )
        Label = "trusted-host"
    }
)
foreach ($attempt in 1..$pipAttempts.Count) {
    $spec = $pipAttempts[$attempt - 1]
    if ($attempt -gt 1) {
        Write-Warn "$($spec.Label) $attempt/$($pipAttempts.Count)"
    }
    $pipRc = Invoke-PipInstallRequirements -ExtraArgs $spec.Extra
    if ($pipRc -eq 0) { break }
}
if ($pipRc -ne 0) {
    Write-Warn "pip 종료 코드 $pipRc — 핵심 패키지 import 로 최종 판정합니다"
} else {
    Write-Ok "설치 완료"
}

# ------------------------------------------------------- 5. .env 준비
Write-Step "환경 설정(.env) 준비"

$EnvFile = Join-Path $Root ".env"
$EnvSample = Join-Path $Root ".env.example"

if (Test-Path $EnvFile) {
    Write-Ok ".env 이미 존재 — 건드리지 않음"
} elseif (Test-Path $EnvSample) {
    Copy-Item $EnvSample $EnvFile
    Write-Ok ".env.example → .env 복사"
    Write-Info "API 키는 나중에 앱의 시작 위저드에서 넣어도 됩니다"
} else {
    Write-Warn ".env.example 이 없어 건너뜁니다"
}

# ------------------------------------------------------- 6. 검증
Write-Step "설치 검증"

$check = @'
import importlib, sys
missing = []
for mod in ("PyQt6.QtWidgets", "PyQt6.QtWebEngineWidgets", "psutil", "mss",
            "PIL", "markdown", "dotenv", "yaml", "numpy", "cv2",
            "onnxruntime", "openai", "pynput"):
    try:
        importlib.import_module(mod)
    except Exception as exc:
        missing.append("%s (%s)" % (mod, exc.__class__.__name__))
if missing:
    print("MISSING:" + ", ".join(missing))
    sys.exit(1)
print("OK")
'@
$checkFile = Join-Path $Root "_iris_setup_check.py"
Set-Content -Path $checkFile -Value $check -Encoding utf8
$result = & $VenvPy $checkFile
$checkRc = $LASTEXITCODE
Remove-Item $checkFile -ErrorAction SilentlyContinue

# 이전 실패로 비어 있는 .venv 가 재사용된 경우 — 한 번 지우고 재설치 (setup.bat -Recreate 와 동일)
if ($checkRc -ne 0) {
    Write-Warn "핵심 패키지 없음 — .venv 재생성 후 1회 재설치합니다"
    try {
        if (Test-Path $VenvPath) { Remove-Item -Recurse -Force $VenvPath }
        & $PyExe @PyArgs -m venv $VenvPath
        if (-not (Test-VenvUsable $VenvPath)) { throw "venv recreate failed" }
        $VenvPy = Join-Path $VenvPath "Scripts\python.exe"
        $trusted = @(
            "--trusted-host", "pypi.org",
            "--trusted-host", "files.pythonhosted.org",
            "--trusted-host", "pypi.python.org"
        )
        $null = Invoke-PipInstallRequirements -ExtraArgs $trusted
        Set-Content -Path $checkFile -Value $check -Encoding utf8
        $result = & $VenvPy $checkFile
        $checkRc = $LASTEXITCODE
        Remove-Item $checkFile -ErrorAction SilentlyContinue
    } catch {
        Write-Warn "재설치 복구 중 오류: $($_.Exception.Message)"
        $checkRc = 1
    }
}

if ($checkRc -ne 0) {
    $pipHint = Get-PipLogErrorTail
    if ($pipHint) {
        $msg = "패키지 설치 실패: $pipHint"
    } else {
        $short = "$result"
        if ($short.Length -gt 160) { $short = $short.Substring(0, 160) + "..." }
        $msg = "핵심 패키지 검증 실패: $short"
    }
    Fail $msg @(
        "인터넷 연결 확인 후 setup.bat 재실행",
        "상세 로그: $PipLog"
    )
}
if ($pipRc -ne 0) {
    Write-Warn "pip 경고가 있었지만 핵심 패키지는 정상입니다"
}
Write-Ok "핵심 패키지 정상 (PyQt6 포함)"
Remove-Item $FailReasonFile -ErrorAction SilentlyContinue

# ------------------------------------------------------- 선택: 음성 런타임
if ($Voice) {
    Write-Host ""
    Write-Host "[선택] 음성 런타임 설치 (.venv-voice)" -ForegroundColor Cyan
    & (Join-Path $Root "scripts\setup_voice_runtime.ps1")
    if (-not $?) { Write-Warn "음성 런타임 설치 실패 — IRIS 본체는 정상 사용 가능합니다" }
}

# ------------------------------------------------------- 마무리
Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "  설치 완료" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "실행:      " -NoNewline; Write-Host ".\run.bat" -ForegroundColor White
Write-Host "첫 실행 시 " -NoNewline; Write-Host "시작 위저드" -ForegroundColor White -NoNewline
Write-Host "가 Ollama · Hermes 설치를 이어서 안내합니다."
Write-Host ""
if (-not $Voice) {
    Write-Host "음성 기능도 쓰려면: " -NoNewline -ForegroundColor DarkGray
    Write-Host ".\setup.ps1 -Voice" -ForegroundColor DarkGray
    Write-Host ""
}

Write-Host "설치 기록: " -NoNewline -ForegroundColor DarkGray
Write-Host "$LogFile · $PipLog" -ForegroundColor DarkGray
Write-Host ""
Stop-Log

if ($Run) {
    Write-Host "IRIS 를 실행합니다..." -ForegroundColor Cyan
    & (Join-Path $Root "run.bat")
}
