# IRIS-Setup.exe 를 GitHub Releases 최신 릴리스로 올린다.
# build_iris_setup.ps1 끝에서 기본 호출. 끌 때: -NoPublish 또는 $env:IRIS_SETUP_NO_PUBLISH=1
[CmdletBinding()]
param(
    [string]$Tag = "",
    [switch]$SkipGitPush
)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Assert-Gh {
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) { throw "gh CLI 없음. https://cli.github.com/ 설치 후 gh auth login" }
    $status = & gh auth status 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "gh 미로그인: gh auth login`n$status" }
}

function New-ReleaseTag {
    $day = (Get-Date).ToString("yyyy.MM.dd")
    $base = "v$day"
    $existing = & gh release list -R kwakminoo/Project-IRIS-Light -L 50 --json tagName -q ".[].tagName" 2>$null
    if ($existing -notcontains $base) { return $base }
    for ($n = 1; $n -le 99; $n++) {
        $cand = "$base.$n"
        if ($existing -notcontains $cand) { return $cand }
    }
    return "v$day.$([guid]::NewGuid().ToString('n').Substring(0,6))"
}

Assert-Gh

$metaPath = Join-Path $Root "docs\download\latest.json"
if (-not (Test-Path $metaPath)) { throw "meta 없음: $metaPath — 먼저 build_iris_setup.ps1 실행" }
$meta = Get-Content $metaPath -Raw -Encoding utf8 | ConvertFrom-Json
$ver = [string]$meta.product_version
$versionedName = [string]$meta.filename
if (-not $ver -or -not $versionedName) { throw "latest.json 에 product_version/filename 없음" }

$dist = Join-Path $Root "dist"
$assets = @(
    (Join-Path $dist $versionedName),
    (Join-Path $dist "$versionedName.sha256"),
    (Join-Path $dist "IRIS-Setup.exe"),
    (Join-Path $dist "IRIS-Setup.exe.sha256"),
    (Join-Path $dist "latest.json")
)
foreach ($a in $assets) {
    if (-not (Test-Path $a)) { throw "에셋 없음: $a" }
}

if (-not $Tag) { $Tag = New-ReleaseTag }

# 메타에 실제 태그 반영 (사이트·검증용)
$meta.tag = $Tag
$meta.published_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$metaJson = ($meta | ConvertTo-Json -Depth 6) + "`n"
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($metaPath, $metaJson, $utf8)
[System.IO.File]::WriteAllText((Join-Path $dist "latest.json"), $metaJson, $utf8)

$rev = ""
try { $rev = (git -C $Root rev-parse --short HEAD).Trim() } catch { }
$notes = @(
    "IRIS Light Setup $ver",
    "",
    "- Windows Setup auto-install: Python bootstrap, stub/PATH harden, pip recovery",
    "- ProductVersion $ver",
    "",
    "Corresponding source: https://github.com/kwakminoo/Project-IRIS-Light",
    "Tag / commit: $Tag / $rev",
    "License: GPL-3.0-or-later (see LICENSE, LICENSE.md)"
) -join "`n"

Write-Host "Publishing release $Tag ($ver) ..."

$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$viewOut = & gh release view $Tag -R kwakminoo/Project-IRIS-Light 2>&1
$viewRc = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($viewRc -eq 0) {
    Write-Host "Release $Tag exists - uploading assets with --clobber"
    & gh release upload $Tag @assets -R kwakminoo/Project-IRIS-Light --clobber
    if ($LASTEXITCODE -ne 0) { throw "gh release upload failed ($LASTEXITCODE)" }
    & gh release edit $Tag -R kwakminoo/Project-IRIS-Light --latest --notes $notes | Out-Null
} else {
    & gh release create $Tag @assets `
        -R kwakminoo/Project-IRIS-Light `
        --title "IRIS Light $Tag" `
        --notes $notes `
        --latest
    if ($LASTEXITCODE -ne 0) { throw "gh release create failed ($LASTEXITCODE)" }
}

Write-Host "Release:" "https://github.com/kwakminoo/Project-IRIS-Light/releases/tag/$Tag"
Write-Host "Download:" "https://github.com/kwakminoo/Project-IRIS-Light/releases/latest/download/$versionedName"

# Site FALLBACK_META = main/docs/download/latest.json
if (-not $SkipGitPush) {
    $candidates = @(
        "docs/download/latest.json",
        "docs/download/IRIS-Setup.exe.sha256",
        ("docs/download/" + $versionedName + ".sha256")
    )
    $toAdd = @()
    foreach ($rel in $candidates) {
        if (Test-Path (Join-Path $Root $rel)) { $toAdd += $rel }
    }
    if ($toAdd.Count -gt 0) {
        & git -C $Root add -- @toAdd
        $staged = @(git -C $Root diff --cached --name-only)
        if ($staged.Count -gt 0) {
            $msg = "Publish IRIS-Setup $ver release metadata ($Tag)."
            & git -C $Root commit -m $msg
            if ($LASTEXITCODE -ne 0) { throw "git commit (download meta) failed" }
            & git -C $Root push origin HEAD
            if ($LASTEXITCODE -ne 0) {
                throw "git push failed - release assets uploaded but latest.json fallback not on main"
            }
            Write-Host "Pushed docs/download meta to origin"
        }
    }
}

Write-Host "verify: powershell -ExecutionPolicy Bypass -File scripts\verify_setup_release.ps1"
