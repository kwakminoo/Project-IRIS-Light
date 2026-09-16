# 설치 프로그램 빌드 · 배포 절차

랜딩 페이지의 「설치 프로그램 내려받기」 버튼은 아래 주소를 고정으로 가리킵니다.

```
https://github.com/kwakminoo/Project-IRIS-Light/releases/latest/download/IRIS-Setup.exe
```

**에셋 이름은 반드시 `IRIS-Setup.exe`** 여야 합니다. 버전을 파일명에 넣으면
(`IRIS-Setup-0.1.1.exe`) 이 주소가 404가 되고 사이트 버튼이 죽습니다. 버전은 릴리스
태그로 구분합니다.

## 0.1.0에서 반드시 고쳐야 하는 것

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

## 번들에서 빼야 하는 것

- `.iris_light_test_tmp/` — 0.1.0에 테스트 잔재(`control_scenario_report.json`)가
  섞여 있었습니다.
- `.venv/`, `.venv-voice/` — 설치 후 `setup.ps1`이 만듭니다.
- `.env` — 사용자 키가 들어갑니다. `.env.example`만 넣습니다.

## 배포

1. 레포 최신 main에서 빌드합니다. 릴리스 노트에 **빌드한 커밋 해시**를 적습니다.
2. 태그 `v0.1.1`로 릴리스를 만들고 에셋 이름을 `IRIS-Setup.exe`로 올립니다.
3. 서명 인증서가 없으므로 Windows SmartScreen이 경고합니다. 랜딩 페이지에
   「추가 정보 → 실행」 안내를 넣어 두었습니다.

## 올리기 전 확인

다른 계정이나 설치 이력이 없는 PC에서:

- [ ] 설치 후 바탕화면 `IRIS` 실행 → 창이 뜹니다
- [ ] `%LOCALAPPDATA%\iris-light\launcher.log` 가 비어 있습니다 (내용이 있으면 기동 실패)
- [ ] 설치 폴더에 `setup-log.txt` · `setup-log-pip.txt` 가 생깁니다
- [ ] 설치 도중 네트워크를 한 번 끊었다 이어도, `setup.bat` 재실행으로 복구됩니다
- [ ] 번들에 `.iris_light_test_tmp` 와 `.env` 가 없습니다
