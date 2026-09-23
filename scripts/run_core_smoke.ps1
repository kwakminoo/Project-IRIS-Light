# Core smoke — startup, gateway, Hermes, control, IDE tile
# Usage: powershell -ExecutionPolicy Bypass -File scripts\run_core_smoke.ps1
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
    Write-Host "WARN: .venv missing — using '$py'" -ForegroundColor Yellow
}

$checks = @(
    "iris.ui._check_iris_startup",
    "iris.system._check_gateway_setup_step",
    "iris.ui._check_hermes_required",
    "iris.ui._check_control_scenarios",
    "iris.ui._check_iris_ide_companion_tile"
)

$failed = 0
$ran = 0
foreach ($mod in $checks) {
    Write-Host "`n=== $mod ===" -ForegroundColor Cyan
    & $py -m $mod
    $code = $LASTEXITCODE
    $ran++
    if ($null -eq $code) { $code = 0 }
    if ($code -ne 0) {
        Write-Host "FAIL $mod (exit $code)" -ForegroundColor Red
        $failed++
    } else {
        Write-Host "OK   $mod" -ForegroundColor Green
    }
}

Write-Host "`n--- core smoke: $ran ran, $failed failed ---"
if ($failed -gt 0) { exit 1 }
exit 0
