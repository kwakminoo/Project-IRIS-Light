#Requires -Version 5.1
<#
.SYNOPSIS
  프로젝트 .env / .env.example 의 「Hermes 주석 키」를 %LOCALAPPDATA%\hermes\.env 에 병합.

.DESCRIPTION
  줄 형태 `# KEY=value` 또는 `KEY=value` 중 Hermes 대상 키만 upsert.
  Iris IRIS_* 키는 건드리지 않는다.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$SrcCandidates = @(
    (Join-Path $Root ".env"),
    (Join-Path $Root ".env.example")
)
$Src = $SrcCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Src) {
    Write-Error "No .env or .env.example in $Root"
}

$HermesHome = Join-Path $env:LOCALAPPDATA "hermes"
$HermesEnv = Join-Path $HermesHome ".env"
New-Item -ItemType Directory -Force -Path $HermesHome | Out-Null
if (-not (Test-Path $HermesEnv)) {
    Set-Content -Path $HermesEnv -Value "# Hermes Agent Environment Configuration`n" -Encoding UTF8
}

$HermesKeys = @(
    "API_SERVER_ENABLED",
    "API_SERVER_KEY",
    "SERPAPI_API_KEY",
    "SERPAPI_DEFAULT_ENGINE",
    "EXA_API_KEY",
    "FIRECRAWL_API_KEY",
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
    "TERMINAL_MODAL_IMAGE",
    "TERMINAL_TIMEOUT",
    "TERMINAL_LIFETIME_SECONDS",
    "BROWSERBASE_PROXIES",
    "BROWSERBASE_ADVANCED_STEALTH",
    "BROWSER_SESSION_TIMEOUT",
    "BROWSER_INACTIVITY_TIMEOUT",
    "WEB_TOOLS_DEBUG",
    "VISION_TOOLS_DEBUG",
    "MOA_TOOLS_DEBUG",
    "IMAGE_TOOLS_DEBUG"
)

$incoming = @{}
Get-Content -Path $Src -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -match '^\s*#\s*([A-Za-z0-9_]+)=(.*)$' -or $line -match '^\s*([A-Za-z0-9_]+)=(.*)$') {
        $k = $Matches[1]
        $v = $Matches[2]
        if ($HermesKeys -contains $k) {
            $incoming[$k] = $v
        }
    }
}

if ($incoming.Count -eq 0) {
    Write-Error "No Hermes keys found in $Src (expected # KEY=value comments)."
}

$existing = Get-Content -Path $HermesEnv -Encoding UTF8
$out = New-Object System.Collections.Generic.List[string]
$seen = @{}

foreach ($line in $existing) {
    if ($line -match '^\s*([A-Za-z0-9_]+)=') {
        $k = $Matches[1]
        if ($incoming.ContainsKey($k)) {
            $out.Add("$k=$($incoming[$k])")
            $seen[$k] = $true
            continue
        }
    }
    $out.Add($line)
}

foreach ($k in $incoming.Keys) {
    if (-not $seen.ContainsKey($k)) {
        $out.Add("$k=$($incoming[$k])")
    }
}

Set-Content -Path $HermesEnv -Value $out -Encoding UTF8
Write-Host "Updated $HermesEnv ($($incoming.Count) keys from $Src)"
Write-Host "Restart Hermes gateway if it was already running: hermes gateway stop --all ; then start Iris or hermes gateway run"
