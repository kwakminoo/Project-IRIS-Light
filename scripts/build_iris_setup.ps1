# IRIS Windows Setup.exe 빌드 — 현재 워크스페이스 소스를 설치 패키지로 묶는다.
# 출력: dist\IRIS-Setup.exe  (파일명에 버전을 넣지 않는다 — 랜딩 페이지가
#       releases/latest/download/IRIS-Setup.exe 를 고정으로 가리킨다)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$InstallerDir = Join-Path $Root "installer"
$Payload = Join-Path $InstallerDir "payload"
$Iss = Join-Path $InstallerDir "iris.iss"
$Icon = Join-Path $Root "iris\assets\iris_icon.ico"
$Exe = Join-Path $Root "dist\IRIS.exe"

# 번들에 절대 들어가면 안 되는 것들. 테스트 잔재·가상환경·사용자 키·설치 로그.
$ExcludeDirs = @(
    "__pycache__", ".pytest_cache", ".mypy_cache", ".git",
    ".venv", ".venv-voice", ".iris_light_test_tmp"
)
$ExcludeFiles = @(".env", "setup-log.txt", "setup-log-pip.txt", "*.pyc", "_build_exe.log")

# 설치 폴더 기준 상대 경로가 이보다 길면 MAX_PATH(260)에 걸려 설치가 롤백된다.
# installer\iris.iss 의 MyDeepestRelPath 와 같이 움직여야 한다.
$MaxRelPathLen = 117

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

# $ExtraExcludeDirs 는 /XD 목록 뒤에 이어 붙는다 — /XF 뒤로 가면 파일 제외로 해석된다.
function Invoke-Robocopy([string]$From, [string]$To, [string[]]$ExtraExcludeDirs) {
    if (-not (Test-Path $From)) { return }
    $null = New-Item -ItemType Directory -Force -Path $To
    $rcArgs = @($From, $To, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP") +
              @("/XD") + $ExcludeDirs + $ExtraExcludeDirs +
              @("/XF") + $ExcludeFiles
    & robocopy @rcArgs | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed ($LASTEXITCODE): $From -> $To"
    }
}

function Assert-PayloadClean([string]$PayloadRoot) {
    $bad = @()
    foreach ($d in $ExcludeDirs) {
        if ($d -eq "__pycache__") { continue }
        $bad += Get-ChildItem -Path $PayloadRoot -Recurse -Force -Directory -Filter $d -ErrorAction SilentlyContinue
    }
    foreach ($f in @(".env", "setup-log.txt", "setup-log-pip.txt")) {
        $bad += Get-ChildItem -Path $PayloadRoot -Recurse -Force -File -Filter $f -ErrorAction SilentlyContinue
    }
    if ($bad.Count -gt 0) {
        $names = ($bad | ForEach-Object { $_.FullName.Substring($PayloadRoot.Length + 1) }) -join "`n  "
        throw "번들에 들어가면 안 되는 항목이 남아 있다:`n  $names"
    }

    $prefix = $PayloadRoot.Length + 1
    $long = Get-ChildItem -Path $PayloadRoot -Recurse -Force -File |
        Where-Object { $_.FullName.Length - $prefix -gt $MaxRelPathLen }
    if ($long) {
        $names = ($long | ForEach-Object {
            "$($_.FullName.Length - $prefix)  $($_.FullName.Substring($prefix))"
        }) -join "`n  "
        throw ("상대 경로가 ${MaxRelPathLen}자를 넘는 파일이 있다. " +
               "iris.iss 의 MyDeepestRelPath 와 이 스크립트의 MaxRelPathLen 을 같이 올려야 한다:`n  $names")
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

$issText = Get-Content $Iss -Raw
$Version = "unknown"
if ($issText -match '#define\s+MyAppVersion\s+"([^"]+)"') { $Version = $Matches[1] }

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
    "node_modules", "lib", "plugins", ".theia"
)
Invoke-Robocopy (Join-Path $Root "android-emulator") (Join-Path $Payload "android-emulator") @(
    "avd", "data"
)

$payloadDist = Join-Path $Payload "dist"
New-Item -ItemType Directory -Force -Path $payloadDist | Out-Null
Copy-Item -Force $Exe (Join-Path $payloadDist "IRIS.exe")

# 설치본은 .git 이 없으므로 REVISION 으로 업데이트 기준을 남긴다.
$revFile = Join-Path $Payload "REVISION"
try {
    $sha = (git -C $Root rev-parse HEAD).Trim()
    if ($sha) {
        [System.IO.File]::WriteAllText($revFile, "$sha`n")
        Write-Host "REVISION $sha"
    }
} catch {
    Write-Host "REVISION skip:" $_
}

# .env 는 사용자 키가 들어간다. .env.example 만 넣는다.
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

Write-Host "Verifying payload ..."
Assert-PayloadClean $Payload

Write-Host "Compiling Setup.exe (v$Version) ..."
& $Iscc $Iss
if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }

$out = Join-Path $Root "dist\IRIS-Setup.exe"
if (-not (Test-Path $out)) { throw "출력 파일 없음: $out" }

# ponytail: Authenticode는 PFX/비밀번호가 있을 때만. 없으면 SmartScreen 경고 유지 — docs/code-signing.md
$codeSigned = $false
$pfx = $env:IRIS_CODE_SIGN_PFX
$pfxPass = $env:IRIS_CODE_SIGN_PASSWORD
if ($pfx -and (Test-Path $pfx) -and $pfxPass) {
    $signTool = $null
    $kitBin = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    if (Test-Path $kitBin) {
        $signTool = Get-ChildItem $kitBin -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
            Sort-Object FullName -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $signTool) {
        $cmd = Get-Command signtool -ErrorAction SilentlyContinue
        if ($cmd) { $signTool = $cmd.Source }
    }
    if (-not $signTool) {
        throw "IRIS_CODE_SIGN_PFX 가 있으나 signtool.exe 없음 (Windows SDK 설치 필요)"
    }
    $ts = if ($env:IRIS_CODE_SIGN_TIMESTAMP) { $env:IRIS_CODE_SIGN_TIMESTAMP } else { "http://timestamp.digicert.com" }
    Write-Host "Authenticode 서명: $signTool"
    & $signTool sign /fd SHA256 /f $pfx /p $pfxPass /tr $ts /td SHA256 $out
    if ($LASTEXITCODE -ne 0) { throw "signtool sign failed ($LASTEXITCODE)" }
    & $signTool verify /pa $out
    if ($LASTEXITCODE -ne 0) { throw "signtool verify failed ($LASTEXITCODE)" }
    $codeSigned = $true
} else {
    Write-Host "코드 서명 스킵 (IRIS_CODE_SIGN_PFX/PASSWORD 없음). docs/code-signing.md 참고."
}

$size = (Get-Item $out).Length
$product = ((Get-Item $out).VersionInfo.ProductVersion).Trim()
$hash = (Get-FileHash $out -Algorithm SHA256).Hash.ToLowerInvariant()
$shaFile = Join-Path $Root "dist\IRIS-Setup.exe.sha256"
[System.IO.File]::WriteAllText($shaFile, "$hash  IRIS-Setup.exe`n")

$downloadDir = Join-Path $Root "docs\download"
New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
Copy-Item -Force $shaFile (Join-Path $downloadDir "IRIS-Setup.exe.sha256")

$tagHint = ""
try {
    $tagHint = (git -C $Root describe --tags --abbrev=0 2>$null).Trim()
} catch { }

$meta = [ordered]@{
    schema             = "iris-setup-release/v1"
    filename           = "IRIS-Setup.exe"
    display_filename   = "IRIS-Setup-$product.exe"
    product_version    = $product
    tag                = $tagHint
    published_at       = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    size_bytes         = $size
    sha256             = $hash
    download_url       = "https://github.com/kwakminoo/Project-IRIS-Light/releases/latest/download/IRIS-Setup.exe"
    checksum_url       = "https://github.com/kwakminoo/Project-IRIS-Light/releases/latest/download/IRIS-Setup.exe.sha256"
    releases_url       = "https://github.com/kwakminoo/Project-IRIS-Light/releases"
    site_install_url   = "https://iris-light-site.vercel.app/#install"
    code_signed        = $codeSigned
    notes              = "Asset name stays IRIS-Setup.exe for stable /latest/download URL. Version is in tag + this metadata."
    requirements       = [ordered]@{
        os   = "Windows 10/11 (x64)"
        ram  = "8GB (권장 16GB)"
        disk = "약 20GB (첫 설치·모델 포함)"
        gpu  = "불필요 (기본 클라우드 모델)"
    }
}
$metaPath = Join-Path $downloadDir "latest.json"
$meta | ConvertTo-Json -Depth 4 | Set-Content -Path $metaPath -Encoding utf8
Copy-Item -Force $metaPath (Join-Path $Root "dist\latest.json")

Write-Host "OK:" (Resolve-Path $out) "($([math]::Round($size/1MB, 1)) MB, ProductVersion $product)"
Write-Host "SHA-256: $hash"
Write-Host "메타:" (Resolve-Path $metaPath)
Write-Host "릴리스 에셋: IRIS-Setup.exe + IRIS-Setup.exe.sha256 (+ 선택 latest.json). 버전은 태그로 구분."
Write-Host "업로드 후: powershell -ExecutionPolicy Bypass -File scripts\verify_setup_release.ps1"
