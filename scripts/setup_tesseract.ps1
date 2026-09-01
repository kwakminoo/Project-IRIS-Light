# IRIS — Tesseract OCR 설치·연결 (Windows)
#   powershell -ExecutionPolicy Bypass -File scripts\setup_tesseract.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$tesseractExe = "C:\Program Files\Tesseract-OCR\tesseract.exe"

Write-Host "[1/4] Tesseract OCR 설치 확인..."
if (-not (Test-Path $tesseractExe)) {
    Write-Host "  winget으로 Tesseract 설치 중..."
    winget install UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements --disable-interactivity
    if (-not (Test-Path $tesseractExe)) {
        throw "Tesseract 설치 후에도 $tesseractExe 를 찾을 수 없습니다."
    }
}
& $tesseractExe --version | Select-Object -First 1

Write-Host "[2/4] Python OCR 패키지 설치..."
if (-not (Test-Path $venvPy)) {
    throw ".venv 가 없습니다. 프로젝트 루트에서 venv 를 먼저 만드세요."
}
& (Join-Path $root ".venv\Scripts\pip.exe") install pytesseract pymupdf -q

Write-Host "[3/4] tessdata(kor) 부트스트랩 + 연결 검증..."
$env:TESSERACT_CMD = $tesseractExe
& $venvPy -m iris.ui._check_pdf_ocr
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[4/4] 완료"
Write-Host "  tesseract: $tesseractExe"
Write-Host "  tessdata : $env:LOCALAPPDATA\iris\tesseract\tessdata"
Write-Host "  IRIS 스캔 PDF 위키 import 를 사용할 수 있습니다."
