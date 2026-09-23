# 설치 프로그램 빌드 · 배포 절차

랜딩 페이지(`https://iris-light-site.vercel.app/#install`)는 `docs/download/latest.json`의
`download_url`을 읽어서 **버전 파일명**으로 받습니다.

예:

```
https://github.com/kwakminoo/Project-IRIS-Light/releases/latest/download/IRIS-Setup-0.1.5.exe
```

브라우저 저장 이름이 `IRIS-Setup-0.1.5.exe`처럼 버전을 포함합니다.

안정 별칭(북마크·구 링크용)도 같이 올립니다.

```
https://github.com/kwakminoo/Project-IRIS-Light/releases/latest/download/IRIS-Setup.exe
```

## 릴리스에 올릴 에셋

| 에셋 | 역할 |
|------|------|
| `IRIS-Setup-<version>.exe` | **기본 다운로드** (버전이 파일명에 보임) |
| `IRIS-Setup-<version>.exe.sha256` | 버전 파일 SHA-256 |
| `IRIS-Setup.exe` | 안정 별칭 (동일 바이너리 복사) |
| `IRIS-Setup.exe.sha256` | 별칭 SHA-256 |
| `latest.json` | 사이트·검증 메타 (`download_url` = 버전 파일) |

GitHub CDN이 최종 응답에 넣는 헤더(정상 시):

- `Content-Type: application/octet-stream`
- `Content-Disposition: attachment; filename=IRIS-Setup-<version>.exe`
- `Content-Length` · `Accept-Ranges: bytes` · HTTPS

`scripts\verify_setup_release.ps1` 이 최종 헤더·PE 매직·해시를 검사합니다.

## F1~F5 — 사이트가 할 수 있는 것 / 없는 것

| 코드 | 원인 | 사이트·릴리스로 완화 | 코드만으로 불가 |
|------|------|----------------------|-----------------|
| F1 | Drive/Gmail/메신저/기업 메일이 `.exe` 차단 | 공식 GitHub Releases HTTPS만 안내, 메신저 전달 금지 | 제3자 정책 우회 |
| F2 | 브라우저·SmartScreen·EDR 경고 | 서명 안내, 「추가 정보 → 실행」, IT 문의 | 평판·정책 자체 |
| F3 | 확장자 변형·빈/불완전 파일 | SHA-256·크기 표시, 검증 스크립트 | — |
| F4 | 미서명·Zone.Identifier를 「파일 형식」으로 오인 | SmartScreen vs 형식 오류 문구 분리 | — |
| F5 | 앱 `ATTACHMENT_UNSUPPORTED_TYPE` 오인 | 오류 코드·도움말 URL 분리 | — |

**금지:** EXE 확장자 위장, 암호 ZIP 숨김, 메신저/메일 우회 배포.

## 빌드

```powershell
# Inno Setup 이 없으면: winget install -e --id JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File scripts\build_iris_setup.ps1
```

산출물:

- `dist\IRIS-Setup.exe`
- `dist\IRIS-Setup-<version>.exe`
- 대응 `.sha256` · `docs\download\latest.json` · `dist\latest.json`

코드 서명은 인증서가 있을 때만 (`docs/code-signing.md`).

버전을 올릴 때는 `installer\iris.iss` 의 `MyAppVersion` 한 곳만 고칩니다.

## 대응 소스 (GPL-3.0 §6)

바이너리(`IRIS-Setup*.exe`, thin launcher `dist/IRIS.exe`)를 배포할 때 대응 소스는
**이 공개 저장소**입니다. 릴리스 노트에 아래를 그대로 넣습니다.

```text
Corresponding source: https://github.com/kwakminoo/Project-IRIS-Light
Tag / commit: <RELEASE_TAG or REVISION>
License: GPL-3.0-or-later (see LICENSE, LICENSE.md)
```

## 배포

1. 최신 main에서 빌드. 릴리스 노트에 **빌드 커밋 해시**(`REVISION`)와 **대응 소스 URL**을 적습니다.
2. 태그로 릴리스를 만들고 위 에셋 표를 모두 올립니다.
3. 검증:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_setup_release.ps1
```

4. 서명 없으면 SmartScreen이 경고합니다. 랜딩에 「추가 정보 → 실행」 안내가 있습니다.

`AppId` 는 `{8F3C2A91-4B17-4E6D-9C21-A1B2C3D4E5F6}` 로 고정입니다.

## 사용자 검증 (PowerShell)

```powershell
Get-FileHash .\IRIS-Setup-0.1.5.exe -Algorithm SHA256
# 사이트/릴리스에 게시된 SHA-256 과 비교. 다르면 공식 페이지에서 다시 받으세요.
```

## 올리기 전 확인

- [ ] `verify_setup_release.ps1` OK
- [ ] `ProductVersion` = 올리려는 버전
- [ ] 버전 파일 + `IRIS-Setup.exe` 별칭 둘 다 업로드
- [ ] SHA-256 파일이 같은 해시를 가리킴
- [ ] 설치 후 바탕화면 `IRIS` 실행
- [ ] 번들에 `.iris_light_test_tmp` · `.env` 없음

## 설치본을 뜯어봐야 할 때

Inno Setup 6.4+ 는 로더가 바뀌어 `innoextract` 가 읽지 못합니다.
짧은 경로에 무인 설치하고 로그를 봅니다.

```powershell
.\IRIS-Setup-0.1.5.exe /VERYSILENT /SUPPRESSMSGBOXES /NOICONS /DIR=C:\t\iris /LOG=C:\t\install.log
C:\t\iris\unins000.exe /VERYSILENT
```
