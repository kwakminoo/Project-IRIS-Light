# Hermes 설치 실패 (우회 포함) — 원인 분석 · 개선안

> **작성**: 2026-09-24  
> **재현 환경**: IRIS-Setup 0.1.9 설치 직후 Core 4/10「Hermes 설치」  
> **증상 UI**: `우회 설치도 실패: pip 설치 실패: Obtaining file:///…/hermes-agent` + build dependencies 진행 중 문구  
> **관련 코드**: `iris/system/setup_protocol.py` (`_install_hermes`, `_install_hermes_bypass`), `iris/system/hermes_install.py`

---

## 1. 한줄 결론

| # | 판정 | 내용 |
|---|------|------|
| A | **확정 버그** | pip 실패 메시지를 **로그 앞부분**만 잘라 보여 줌 → 실제 원인 대신 `Obtaining file://…` 가 “실패 이유”로 표시됨 |
| B | **설계상 1차 실패** | 공식 `install.ps1` 은 Windows에서 **uv managed Python junction (WinError 448)** 에 자주 걸려, 의도적으로 우회로 넘어감 |
| C | **우회 경로 취약** | Hermes 업스트림은 `uv sync`+`uv.lock` 전제인데, Iris 우회는 `pip install -e ".[homeassistant,mcp]"` — 느리고 잠금파일 없음, 실패면 원인 로그도 남기지 않음 |
| D | **재현 시 참고** | 동일 PC에서 cwd를 `hermes-agent`로 두고 pip를 다시 돌리면 **성공**함 → “패키지 자체가 영원히 깨짐”보다 **타임아웃·레이스·잘린 진단** 쪽이 유력 |

---

## 2. 현재 설치 파이프라인 (범위 확대)

```
needs_user / auto_install
        │
        ▼
_install_hermes()
  ├─ (깨진 트리면) force_retire_hermes_agent  — rename/robocopy 정리
  ├─ 공식: irm install.ps1 | -SkipSetup -NonInteractive
  │     └─ 내부: uv 로 managed Python + clone + sync
  │           └─ WinError 448 / “untrusted mount” / Python 3.11 link 실패
  │                 └─ looks_like_uv_python_mount_failure(log) → 우회
  └─ _install_hermes_bypass()
        └─ install_hermes_with_system_python()
              ├─ find_bootstrap_python (Iris .venv 우선 → py -3.13/12/11 → winget 3.11)
              ├─ wipe + git clone --depth 1 NousResearch/hermes-agent
              ├─ python -m venv hermes-agent/venv
              ├─ pip install -e ".[homeassistant,mcp]"
              │     └─ 실패 시 pip -e . + aiohttp/mcp 보강
              │           └─ 실패 시 requirements.txt (업스트림에 없음 → 사실상 dead)
              └─ probe_hermes_runtime / import hermes_cli
```

| 계층 | 역할 | 실패하면 |
|------|------|----------|
| 공식 스크립트 | 업스트림 권장 경로 | 448 → 우회 |
| 우회 pip | Iris가 직접 clone+venv | UI에 `우회 설치도 실패` |
| probe | `hermes` 실행·API 가능 여부 | `우회 설치 후 런타임 실패` (이번 UI 문구와는 다름) |
| NeedsUser 카드 | 「설치」「완료했어요」 | 원인 없이 재시도만 유도 |

---

## 3. 원인 후보 표 (넓은 범위)

| 연번 | 가설 | 근거 | 이번 UI와의 정합 | 신뢰도 |
|------|------|------|------------------|--------|
| H1 | **실패 메시지 head 절단** | `hermes_install.py` `err = (stderr+stdout)[:400]` → `_install_hermes_bypass` `detail[:200]` | UI가 pip **성공 시작 문구**만 보여 줌 | **확정** |
| H2 | 공식 설치 **uv WinError 448** | 우회 진입 조건·주석; OneDrive/필터 드라이버 흔한 원인 | 우회가 돌았다는 사실과 일치 | **높음** |
| H3 | `_run_streamed` **idle/hard 타임아웃**으로 pip 중도 종료 | idle 900s / hard 3600s; 대용량 wheel 구간은 출력이 뜸해질 수 있음 | returncode≠0 + stdout 앞부분만 노출되면 H1과 합성 | **중간~높음** |
| H4 | wipe 직후 **불완전 clone / 동시 접근** | `force_retire` + 공식 설치 잔존 `bin/`·`node/` + 즉시 clone | Obtaining 직후 build 단계에서 깨질 수 있음 | **중간** |
| H5 | bootstrap Python이 **Iris .venv(3.13)** | Hermes `.python-version`=3.11, `requires-python>=3.11,<3.14` | 재실행 pip는 3.13에서 성공 → 버전 단독 원인은 약함 | **낮음~중간** |
| H6 | extras `.[homeassistant,mcp]` 메타/해석 실패 | 폴백 `pip -e .` 존재; 둘 다 실패해야 H1 메시지 | 가능하나 재현 pip는 extras 성공 | **중간** |
| H7 | `requirements.txt` 폴백 **사문화** | 업스트림에 파일 없음; `uv.lock`만 존재 | 최종 폴백이 실질적으로 없음 | **확정(설계 공백)** |
| H8 | 네트워크/PyPI·미러 일시 장애 | 의존성 수십 개 exact pin | 재시도 성공과 양립 | **중간** |
| H9 | pip 로그를 **디스크에 안 남김** | UI 스트림만, `%LOCALAPPDATA%\hermes\logs`에 우회 pip 전체 없음 | 원인 파악 불가 → “설치 안 됨”으로만 보임 | **확정(관측)** |
| H10 | 공식 경로만 재시도(「설치」버튼) | NeedsUser가 동일 `_install_hermes` 루프 | 448 환경에서 같은 실패 반복 | **높음** |

---

## 4. 확정 코드 결함 (H1)

```python
# iris/system/hermes_install.py — 실패 시
err = ((stderr or "") + (stdout or ""))[:400]   # ← 앞 400자
return False, f"pip 설치 실패: {err}"

# setup_protocol._install_hermes_bypass
message=f"우회 설치도 실패: {detail[:200]}"     # ← 다시 앞 200자
```

정상 pip도 맨 앞이 `Obtaining file:///…/hermes-agent` + `Installing build dependencies…` 이다.  
그래서 **진짜 실패 줄**(충돌, 타임아웃, wheel build error, PermissionError)이 잘려 나가고, 사용자는 “Obtaining에서 실패”로 오해한다.

권장 수정(최소):

- `combined_install_log_tail` / 기존 `combined_install_log_tail` 헬퍼를 pip 실패에도 사용 (**꼬리** N자).
- `%LOCALAPPDATA%\hermes\logs\iris-bypass-pip-<stamp>.log` 에 **전체** stdout 저장.
- UI 메시지: `pip 실패 (로그: …)\n` + 꼬리 8~12줄.

---

## 5. 개선안 총괄표

| 연번 | 구분 | 사항 | 위치 | 등급 | 권장 조치 | 기대 효과 |
|:---:|------|------|------|------|-----------|-----------|
| 1 | 관측 | 실패 사유 head 절단 | `hermes_install.py`, `_install_hermes_bypass` | **긴급** | 꼬리 추출 + 전체 로그 파일 + UI에 경로 표시 | 원인 식별 가능 |
| 2 | 안정 | 공식 실패 시 우회를 “448만”이 아니라 **넓게** | `_install_hermes` | **중요** | `probe` 실패 + 공식 rc≠0 이면 항상 우회 1회 (이미 일부 있음, 조건 단순화) | 448 로그 누락 시에도 복구 |
| 3 | 안정 | 우회를 **uv sync** 우선 | `hermes_install.py` | **중요** | 시스템/Iris Python으로 venv 만든 뒤 `uv sync --frozen` (있으면), 실패 시 pip | 업스트림과 동일 lock |
| 4 | 안정 | bootstrap Python **3.11/3.12 우선** | `find_bootstrap_python` | **중요** | Iris 3.13보다 `py -3.11`/`-3.12` 우선, 없으면 winget 3.11 | `.python-version` 정합 |
| 5 | 안정 | clone 전 **완전 격리 디렉터리** | `install_hermes_with_system_python` | 보통 | `hermes-agent.staging-<stamp>` clone → 성공 시 rename swap | wipe 레이스 제거 |
| 6 | UX | NeedsUser에 **로그 열기 / 우회만 재시도** | `setup_wizard` | **중요** | 「로그 열기」「우회로 다시 설치」 버튼 | 공식 448 루프 탈출 |
| 7 | 관측 | Core 단계별 `last_error` 구조화 | setup state JSON | 보통 | `{step, kind, log_path, tail}` 저장 | 지원·재현 |
| 8 | 폴백 | dead `requirements.txt` 경로 | `hermes_install.py` | 보통 | 제거하거나 `uv export`/`pip install` from lock 로 교체 | 가짜 폴백 제거 |
| 9 | 타임아웃 | pip quiet 구간 idle 오탐 | `_run_streamed` + bypass | 보통 | pip 단계만 idle 완화(heartbeat 줄 emit) 또는 progress hook | 중도 살해 감소 |
| 10 | 문서 | 사이트/위저드 안내 | README · wizard hint | 참고 | “Windows에서 OneDrive 하위 LOCALAPPDATA면 uv 448 → Iris 우회 사용” | 기대치 정렬 |
| 11 | 테스트 | 우회 실패 메시지 회귀 | `tests/test_hermes_install_bypass.py` | **중요** | fake pip stdout 앞에 Obtaining·뒤에 ERROR → 사용자 메시지에 ERROR 포함 assert | H1 재발 방지 |
| 12 | 운영 | Setup 패키지에 Hermes **사전 번들 금지** vs 캐시 | 배포 | 참고 | 번들은 비대; 대신 실패 시 재시도·미러 URL | 유지 |

---

## 6. 우선 구현 순서 (단기)

1. **연번 1 + 11** — 꼬리 로그·파일·단위 테스트 (반나절)  
2. **연번 2 + 6** — 우회 진입 단순화 + UI「우회만 재시도/로그」 (1일)  
3. **연번 4 + 5** — Python 선택·staging clone (1일)  
4. **연번 3 + 8 + 9** — uv sync 우선·폴백 정리·idle (1~2일)

---

## 7. 검증 체크리스트

| # | 검증 | 통과 기준 |
|---|------|-----------|
| 1 | 고의로 pip 실패(존재하지 않는 extra) 유도 | UI에 실제 `ERROR:` 줄 + 로그 파일 존재 |
| 2 | uv 448 시뮬레이션(`looks_like_uv…` fixture) | 공식 실패 → 우회 진입 로그 1회 |
| 3 | 오프라인/차단 네트워크 | 실패 메시지에 네트워크/타임아웃 꼬리, Obtaining만 아님 |
| 4 | 정상 PC cold install | Core 4 Hermes `done`, `hermes.exe`·import·gateway probe OK |
| 5 | 이미 깨진 `%LOCALAPPDATA%\hermes` | wipe 후 재설치 성공, trash 잔존 ≤3 |

```powershell
.venv\Scripts\python.exe -m unittest tests.test_hermes_install_bypass -v
.venv\Scripts\python.exe -m iris.ui._check_setup_hermes_live
```

---

## 8. 지금 테스트 PC에서 할 수 있는 즉시 조치 (코드 배포 전)

위저드가 떠 있는 동안에도, 동일 우회가 **수동으로는 이미 성공 가능**한 상태일 수 있다.

1. 위저드에서 「완료했어요」 전에 터미널로 확인:  
   `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\hermes.exe --version`  
2. 되면 위저드 「완료했어요」로 재검증.  
3. 안 되면 Core「설치」대신, 배포에 연번 1 반영된 Setup을 다시 받아 **실패 로그 꼬리**를 확보한 뒤 재시도.

---

## 9. 상태

| 항목 | 상태 |
|------|------|
| 원인 범위 조사 | 완료 (본 문서) |
| H1 코드 수정 | **미착수** — 다음 작업 |
| 우회 uv sync / UI 버튼 | 미착수 |
| 타 사용자 재현 로그 | UI 스크린샷만 (전체 pip 로그 없음 — H9) |

---

## 10. 이력

| 날짜 | 내용 |
|------|------|
| 2026-09-24 | Core 4 Hermes 우회 실패 UI 기준으로 원인 표·개선안 작성. H1(로그 head 절단) 확정, 동일 트리 pip 재실행 성공 관측 |
