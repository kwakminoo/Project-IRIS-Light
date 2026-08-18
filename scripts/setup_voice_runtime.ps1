param(
    [string]$PythonExe = "py",
    [string]$VenvPath = ".venv-voice",
    [switch]$Full
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path $VenvPath)) {
    & $PythonExe -3 -m venv $VenvPath
}

$Py = Join-Path $VenvPath "Scripts/python.exe"
$Pip = Join-Path $VenvPath "Scripts/pip.exe"

& $Py -m pip install --upgrade pip
& $Pip install -r "services/voice_runtime/requirements-voice-mock.txt"
& $Pip install -r "services/voice_runtime/requirements-voice.txt"

if ($Full) {
    Write-Host "Installing full voice models (CUDA torch, qwen-tts, Faster Qwen streaming)..."
    & $Pip install torch --index-url https://download.pytorch.org/whl/cu128
    & $Pip install qwen-tts
    & $Pip install -r "services/voice_runtime/requirements-voice-full.txt"
}

Write-Host "voice runtime ready:" $Py
Write-Host "Iris TTS 기본: mock 해제 (Qwen). 개발 검증만 VOICE_RUNTIME_MOCK=1"
Write-Host "bind: 127.0.0.1:18765 only (8765 is Iris control surface)"
if (-not $Full) {
    Write-Host "tip: re-run with -Full to install torch/qwen-tts for real TTS"
}
