# 설치 프로그램 빌드 · 배포 절차

랜딩 페이지의 「설치 프로그램 내려받기」 버튼은 `releases/latest/download/IRIS-Setup.exe`
주소를 고정으로 가리킵니다.

**에셋 이름은 반드시 `IRIS-Setup.exe`** 여야 합니다. 버전을 파일명에 넣으면
(`IRIS-Setup-0.1.1.exe`) 이 주소가 404가 되고 사이트 버튼이 죽습니다. 버전은 릴리스
태그로 구분합니다. 빌드 스크립트가 이미 `dist\IRIS-Setup.exe` 로 내보내므로
**이름을 바꾸지 말고 그대로 올리면 됩니다.**

## 지금 어디에 올라가 있나 (2026-09-16)

이 저장소에는 아직 `IRIS-Setup.exe` 릴리스가 없어서 버튼이 404 였습니다. 링크를 살리려고
0.1.1 을 포크에 올려 두었고, 사이트는 **임시로** 그쪽을 가리킵니다.

```
https://github.com/cjh030906/Project-IRIS-Light/releases/tag/v0.1.1
```

**이 저장소에 `v0.1.1` 릴리스를 올리면** 사이트 저장소
(`cjh030906/iris-light-site`)의 `index.html` 에서 `cjh030906/Project-IRIS-Light/releases`
두 줄을 `kwakminoo/...` 로 되돌리면 됩니다. 그 두 줄 말고는 바꾼 게 없습니다.
이 저장소 `README.md` 의 내려받기 링크도 그때 같이 살아납니다.

## 빌드

```powershell
# Inno Setup 이 없으면: winget install -e --id JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File scripts\build_iris_setup.ps1
```

`installer\iris.iss` 와 `scripts\build_iris_setup.ps1` 이 레포에 있습니다. 스크립트는
현재 워크스페이스를 `installer\payload\` 로 스테이징하고 → 번들 검증 → ISCC 컴파일 →
`dist\IRIS-Setup.exe` 순서로 진행합니다. `dist\IRIS.exe`(thin launcher)가 없으면
`scripts\build_iris_exe.ps1` 을 먼저 돌립니다.

버전을 올릴 때는 `installer\iris.iss` 의 `MyAppVersion` 한 곳만 고칩니다
(`AppVersion`·`VersionInfoVersion`·`ProductVersion` 이 전부 여기서 나옵니다).

## 0.1.0에서 고친 것

0.1.0으로 설치하면 앱이 조용히 안 뜨는 경우가 있었습니다. 원인은 두 가지였고
둘 다 레포 main에 수정이 들어가 있습니다. **수정이 들어간 커밋 이후로 다시 빌드해야
합니다.**

1. **무음 사망** — `IRIS_launcher.py`가 `pythonw -m iris`를 띄우고 즉시 종료해서,
   콘솔 없는 `pythonw`가 뱉는 `ModuleNotFoundError`가 어디에도 안 남았습니다.
   이제 런처가 10초간 지켜보다가 즉사하면 이유를 창으로 보여 주고
   `%LOCALAPPDATA%\iris-light\launcher.log`에 남깁니다.
   → **번들하는 `dist/IRIS.exe`를 반드시 새로 빌드**하세요
   (`scripts\build_iris_exe.ps1`, 또는 `python -m PyInstaller --noconfirm --clean IRIS.spec`).

2. **설치 로그 없음** — 설치 후 `setup.ps1`이 만드는 `.venv`에서 pip이 중간에 끊기면
   흔적이 없었습니다. 이제 `setup-log.txt`(진행 기록)와 `setup-log-pip.txt`
   (pip `--log`, 타임스탬프 포함)를 남기고, pip 실패 시 재시도합니다.

3. **설치 프로그램판 무음 사망** — `[Run]` 은 `setup.ps1` 의 종료 코드를 버립니다.
   pip이 실패해도 설치 프로그램은 성공으로 끝나고, 사용자는 앱이 안 뜨고 나서야
   알았습니다. 이제 `[Code]` 의 `CurStepChanged` 에서 실행해 종료 코드를 확인하고,
   실패하면 `setup.bat` 재실행 안내와 로그 경로를 창으로 보여 주며
   「Launch IRIS now」 체크박스를 띄우지 않습니다.

4. **긴 설치 경로** — 번들에서 가장 깊은 파일이 설치 폴더 기준 117자입니다
   (`integrations\showui-aloha\...\trajectory_refiner.txt`). 설치 폴더가 길면
   MAX_PATH(260)에 걸려 `MoveFile code 3` 으로 설치가 통째로 롤백됩니다.
   이제 폴더 선택 화면과 `PrepareToInstall`(무인 설치용)에서 미리 막습니다.

## 번들에서 빼야 하는 것

빌드 스크립트가 robocopy 제외와 `Assert-PayloadClean` 검증으로 두 번 막습니다.
하나라도 남아 있으면 **컴파일 전에 빌드가 실패합니다.**

- `.iris_light_test_tmp/` — 0.1.0에 테스트 잔재(`control_scenario_report.json`)가
  섞여 있었습니다.
- `.venv/`, `.venv-voice/` — 설치 후 `setup.ps1`이 만듭니다.
- `.env` — 사용자 키가 들어갑니다. `.env.example`만 넣습니다.
- `setup-log.txt`, `setup-log-pip.txt` — 설치할 때 생기는 로그입니다.

상대 경로가 117자를 넘는 파일이 새로 생겨도 빌드가 실패합니다. 그때는
`scripts\build_iris_setup.ps1` 의 `MaxRelPathLen` 과 `installer\iris.iss` 의
`MyDeepestRelPath` 를 **같이** 올리고, 설치 경로 여유가 그만큼 줄어드는 걸 감안하세요.

## 배포

1. 레포 최신 main에서 빌드합니다. 릴리스 노트에 **빌드한 커밋 해시**를 적습니다.
2. 태그 `v0.1.1`로 릴리스를 만들고 `dist\IRIS-Setup.exe` 를 **이름 그대로** 올립니다.
3. 서명 인증서가 없으므로 Windows SmartScreen이 경고합니다. 랜딩 페이지에
   「추가 정보 → 실행」 안내를 넣어 두었습니다.

`AppId` 는 `{8F3C2A91-4B17-4E6D-9C21-A1B2C3D4E5F6}` 로 고정입니다. 이 값이 바뀌면
덮어쓰기 업그레이드가 안 되고 IRIS가 두 벌 깔립니다.

## 올리기 전 확인

다른 계정이나 설치 이력이 없는 PC에서:

- [ ] 빌드 로그 마지막 줄의 `ProductVersion` 이 올리려는 버전과 같습니다
- [ ] 설치 후 바탕화면 `IRIS` 실행 → 창이 뜹니다
- [ ] `%LOCALAPPDATA%\iris-light\launcher.log` 가 비어 있습니다 (내용이 있으면 기동 실패)
- [ ] 설치 폴더에 `setup-log.txt` · `setup-log-pip.txt` 가 생깁니다
- [ ] 설치 도중 네트워크를 끊으면 **설치 프로그램이 실패를 알려 줍니다**
      (조용히 끝나면 3번 수정이 빠진 빌드입니다). 이어서 `setup.bat` 재실행으로 복구됩니다
- [ ] 번들에 `.iris_light_test_tmp` 와 `.env` 가 없습니다

## 설치본을 뜯어봐야 할 때

Inno Setup 6.4+ 는 로더가 바뀌어 `innoextract` 가 읽지 못합니다
(`Unexpected setup loader revision: 2`). 대신 짧은 경로에 무인 설치하고 로그를 봅니다.

```powershell
.\IRIS-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NOICONS /DIR=C:\t\iris /LOG=C:\t\install.log
# 로그의 "Dest filename:" 줄이 번들 목록입니다
C:\t\iris\unins000.exe /VERYSILENT   # 정리 (설치 후 생성된 파일은 폴더째 지우세요)
```

`/DIR` 은 반드시 짧게 잡으세요. 위 4번 가드가 긴 경로를 막습니다.
