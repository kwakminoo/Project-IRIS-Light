# Verify IRIS-Setup.exe official download URL, headers, PE magic, SHA256.
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\verify_setup_release.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\verify_setup_release.ps1 -Url <url> -ExpectedSha256 <hex>
[CmdletBinding()]
param(
    [string]$Url = "",
    [string]$ExpectedSha256 = "",
    [string]$MetaPath = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

if (-not $MetaPath) {
    $MetaPath = Join-Path $Root "docs\download\latest.json"
}

$expectedSize = [long]0
$expectedName = "IRIS-Setup.exe"

if (-not $Url -or -not $ExpectedSha256) {
    if (-not (Test-Path $MetaPath)) {
        throw "MetaPath missing: $MetaPath (pass -Url and -ExpectedSha256)"
    }
    $meta = Get-Content $MetaPath -Raw -Encoding utf8 | ConvertFrom-Json
    if (-not $Url) { $Url = [string]$meta.download_url }
    if (-not $ExpectedSha256) { $ExpectedSha256 = [string]$meta.sha256 }
    $expectedSize = [long]$meta.size_bytes
    if ($meta.filename) { $expectedName = [string]$meta.filename }
}

$ExpectedSha256 = $ExpectedSha256.Trim().ToLowerInvariant() -replace '^sha256:', ''
if ($ExpectedSha256 -notmatch '^[0-9a-f]{64}$') {
    throw "ExpectedSha256 is not 64 hex chars: $ExpectedSha256"
}

Write-Host "GET (follow redirects): $Url"
$tmp = Join-Path $env:TEMP ("iris-setup-verify-{0}.exe" -f [guid]::NewGuid().ToString("n"))
try {
    $headerRaw = & curl.exe -sI -L $Url 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "curl headers failed: $LASTEXITCODE" }

    $blocks = $headerRaw -split "(?m)(?=^HTTP/)"
    $final = ($blocks | Where-Object { $_ -match '^HTTP/' } | Select-Object -Last 1)
    if (-not $final) { throw "could not parse final HTTP response" }
    if ($final -notmatch 'HTTP/\S+\s+200\b') {
        throw "final status is not 200:`n$final"
    }

    $ct = if ($final -match '(?im)^Content-Type:\s*(.+)$') { $Matches[1].Trim() } else { "" }
    $cd = if ($final -match '(?im)^Content-Disposition:\s*(.+)$') { $Matches[1].Trim() } else { "" }
    $cl = if ($final -match '(?im)^Content-Length:\s*(\d+)') { [long]$Matches[1] } else { -1 }
    $ar = if ($final -match '(?im)^Accept-Ranges:\s*(.+)$') { $Matches[1].Trim() } else { "" }

    Write-Host "Content-Type: $ct"
    Write-Host "Content-Disposition: $cd"
    Write-Host "Content-Length: $cl"
    Write-Host "Accept-Ranges: $ar"

    if ($ct -match 'text/html') {
        throw "Content-Type is text/html (HTML error page may be saved as .exe)"
    }
    if ($ct -and $ct -notmatch 'octet-stream|x-msdownload|binary|application/exe') {
        Write-Warning "Unexpected Content-Type: $ct (continuing; PE magic check follows)"
    }
    if ($cd -and $cd -notmatch [regex]::Escape($expectedName) -and $cd -notmatch 'IRIS-Setup') {
        Write-Warning "Content-Disposition name may differ: $cd (expected $expectedName)"
    }
    if ($expectedSize -gt 0 -and $cl -gt 0 -and $cl -ne $expectedSize) {
        throw "Content-Length($cl) != meta.size_bytes($expectedSize)"
    }

    & curl.exe -fsSL $Url -o $tmp
    if ($LASTEXITCODE -ne 0) { throw "curl download failed: $LASTEXITCODE" }

    $len = (Get-Item $tmp).Length
    if ($len -lt 1MB) {
        $peek = Get-Content $tmp -TotalCount 5 -ErrorAction SilentlyContinue
        throw "downloaded file too small ($len bytes); HTML/error page suspected:`n$peek"
    }
    if ($expectedSize -gt 0 -and $len -ne $expectedSize) {
        throw "size mismatch: got $len expected $expectedSize"
    }

    $fs = [System.IO.File]::OpenRead($tmp)
    try {
        $b0 = $fs.ReadByte(); $b1 = $fs.ReadByte()
    } finally { $fs.Close() }
    if ($b0 -ne 0x4D -or $b1 -ne 0x5A) {
        throw "not a PE file (missing MZ magic); corrupt or HTML redirect"
    }

    $got = (Get-FileHash $tmp -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host ("hash " + $got)
    if ($got -ne $ExpectedSha256) {
        throw ("hash mismatch`n  expected " + $ExpectedSha256 + "`n  got      " + $got)
    }

    $localSha = Join-Path $Root "docs\download\IRIS-Setup.exe.sha256"
    if (Test-Path $localSha) {
        $line = (Get-Content $localSha -TotalCount 1 -Encoding utf8).Trim()
        $localHash = ($line -split '\s+')[0].ToLowerInvariant()
        if ($localHash -match '^[0-9a-f]{64}$' -and $localHash -ne $got) {
            throw "docs/download/IRIS-Setup.exe.sha256 ($localHash) != downloaded hash"
        }
    }

    Write-Host ("OK url/headers/size/PE/hash match (" + $len + " bytes)")
    exit 0
} finally {
    if (Test-Path $tmp) { Remove-Item -Force $tmp -ErrorAction SilentlyContinue }
}
