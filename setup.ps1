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
$MinMajor = 3
$MinMinor = 11

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

function Fail([string]$Message, [string[]]$Hints) {
    Write-Host ""
    Write-Host "설치 실패: $Message" -ForegroundColor Red
    if ($Hints) {
        Write-Host ""
        Write-Host "해결 방법:" -ForegroundColor Yellow
        foreach ($h in $Hints) { Write-Host "  - $h" }
    }
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Magenta
Write-Host "  IRIS 자동 설치" -ForegroundColor Magenta
Write-Host "  경로: $Root" -ForegroundColor DarkGray
Write-Host "===============================================" -ForegroundColor Magenta

# ------------------------------------------------------- 1. Python 찾기
Write-Step "Python 3.$MinMinor 이상 확인"

function Get-PythonCandidates {
    $out = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $out += ,@("py", @("-3.13"))
        $out += ,@("py", @("-3.12"))
        $out += ,@("py", @("-3.11"))
        $out += ,@("py", @("-3"))
    }
    foreach ($name in @("python", "python3")) {
        if (Get-Command $name -ErrorAction SilentlyContinue) { $out += ,@($name, @()) }
    }
    return $out
}

$PyExe = $null
$PyArgs = @()
$PyVersion = $null

foreach ($cand in Get-PythonCandidates) {
    $exe = $cand[0]
    $argv = $cand[1]
    try {
        $raw = & $exe @argv -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
    } catch { continue }
    if (-not $?) { continue }
    if (-not $raw) { continue }
    $v = ($raw | Select-Object -First 1).Trim()
    $parts = $v.Split(".")
    if ($parts.Count -lt 2) { continue }
    $maj = [int]$parts[0]; $min = [int]$parts[1]
    if ($maj -gt $MinMajor -or ($maj -eq $MinMajor -and $min -ge $MinMinor)) {
        $PyExe = $exe; $PyArgs = $argv; $PyVersion = $v
        break
    }
}

if (-not $PyExe) {
    Fail "Python $MinMajor.$MinMinor 이상을 찾지 못했습니다." @(
        "https://www.python.org/downloads/ 에서 Python 3.12 설치",
        "설치 화면에서 [Add python.exe to PATH] 체크 필수",
        "또는 PowerShell에서: winget install -e --id Python.Python.3.12",
        "설치 후 이 창을 닫고 setup.bat 을 다시 실행하세요"
    )
}
Write-Ok "Python $PyVersion ($PyExe $($PyArgs -join ' '))"

# ------------------------------------------------------- 2. 가상환경
Write-Step "가상환경(.venv) 준비"

if ($Recreate -and (Test-Path $VenvPath)) {
    Write-Info "-Recreate: 기존 .venv 삭제"
    Remove-Item -Recurse -Force $VenvPath
}

$VenvPy = Join-Path $VenvPath "Scripts\python.exe"

if (Test-Path $VenvPy) {
    Write-Ok ".venv 이미 존재 — 재사용 (새로 만들려면 -Recreate)"
} else {
    Write-Info "생성 중..."
    & $PyExe @PyArgs -m venv $VenvPath
    if (-not (Test-Path $VenvPy)) {
        Fail "가상환경 생성에 실패했습니다." @(
            "$PyExe $($PyArgs -join ' ') -m ensurepip 실행 후 재시도",
            "Microsoft Store 버전 Python은 문제가 생길 수 있습니다. python.org 배포판을 권장합니다"
        )
    }
    Write-Ok "생성 완료: $VenvPath"
}

# ------------------------------------------------------- 3. pip 업그레이드
Write-Step "pip 업그레이드"
& $VenvPy -m pip install --upgrade pip --disable-pip-version-check -q
if (-not $?) { Write-Warn "pip 업그레이드 실패 — 기존 pip으로 계속합니다" } else { Write-Ok "pip 최신" }

# ------------------------------------------------------- 4. 의존성 설치
Write-Step "의존성 설치 (requirements.txt) — 수 분 걸릴 수 있습니다"

& $VenvPy -m pip install -r (Join-Path $Root "requirements.txt") --disable-pip-version-check
if (-not $?) {
    Fail "의존성 설치에 실패했습니다." @(
        "네트워크/프록시 상태를 확인하세요",
        "사내망이라면: $VenvPy -m pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org",
        ".\setup.ps1 -Recreate 로 가상환경을 새로 만들어 재시도"
    )
}
Write-Ok "설치 완료"

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
            "PIL", "markdown", "dotenv", "yaml", "numpy"):
    try:
        importlib.import_module(mod)
    except Exception as exc:
        missing.append("%s (%s)" % (mod, exc.__class__.__name__))
if missing:
    print("MISSING:" + ", ".join(missing))
    sys.exit(1)
print("OK")
'@
$checkFile = Join-Path $env:TEMP "iris_setup_check.py"
Set-Content -Path $checkFile -Value $check -Encoding utf8
$result = & $VenvPy $checkFile 2>&1
$checkOk = $?
Remove-Item $checkFile -ErrorAction SilentlyContinue

if (-not $checkOk) {
    Fail "핵심 패키지 import 검증 실패: $result" @(
        ".\setup.ps1 -Recreate 로 재설치",
        "Visual C++ 재배포 패키지가 없으면 PyQt6 로드가 실패할 수 있습니다: winget install -e --id Microsoft.VCRedist.2015+.x64"
    )
}
Write-Ok "핵심 패키지 정상 (PyQt6 포함)"

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

if ($Run) {
    Write-Host "IRIS 를 실행합니다..." -ForegroundColor Cyan
    & (Join-Path $Root "run.bat")
}
