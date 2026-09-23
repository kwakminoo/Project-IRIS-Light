# Windows Authenticode 코드 서명 (운영 체크리스트)

`IRIS-Setup.exe`는 현재 **코드 서명 없음**. SmartScreen 「알 수 없는 게시자」 경고는
평판(다운로드 수·서명)으로만 줄어들며, 웹사이트 코드만으로 제거할 수 없습니다.

## 준비물 (사람이 확보)

| 항목 | 설명 |
|------|------|
| 코드 서명 인증서 | OV/EV Authenticode (PFX 또는 Azure Key Vault / DigiCert KeyLocker 등) |
| 타임스탬프 URL | 예: `http://timestamp.digicert.com` |
| CI secret | `IRIS_CODE_SIGN_PFX` (경로 또는 base64), `IRIS_CODE_SIGN_PASSWORD` |
| SignTool | Windows SDK (`signtool.exe`) — 이 PC에 SDK가 있으면 경로만 잡으면 됨 |

## 빌드 시 서명 (인증서가 있을 때만)

`scripts/build_iris_setup.ps1`은 환경 변수가 있을 때만 서명합니다.

```powershell
$env:IRIS_CODE_SIGN_PFX = "C:\secrets\iris-codesign.pfx"
$env:IRIS_CODE_SIGN_PASSWORD = "<pfx-password>"
# optional:
# $env:IRIS_CODE_SIGN_TIMESTAMP = "http://timestamp.digicert.com"
powershell -ExecutionPolicy Bypass -File scripts\build_iris_setup.ps1
```

서명이 적용되면 `docs/download/latest.json` 의 `code_signed` 가 `true` 로 기록됩니다.

## 수동 서명 예시

```powershell
signtool sign /fd SHA256 /f $env:IRIS_CODE_SIGN_PFX /p $env:IRIS_CODE_SIGN_PASSWORD `
  /tr http://timestamp.digicert.com /td SHA256 `
  dist\IRIS-Setup.exe
signtool verify /pa dist\IRIS-Setup.exe
```

## 배포 후

1. 서명된 `IRIS-Setup.exe` + `IRIS-Setup.exe.sha256` 을 GitHub Release에 업로드
2. `scripts\verify_setup_release.ps1` 실행
3. SmartScreen 평판은 **수일~수주** 걸릴 수 있음 — 사이트 안내에 「추가 정보 → 실행」을 유지

## 하지 말 것

- EXE 확장자 위장, 암호 ZIP으로 숨기기, 메신저/메일 우회 배포
- 자체 서명(self-signed)만으로 SmartScreen 해소된다고 사용자에게 약속하기
