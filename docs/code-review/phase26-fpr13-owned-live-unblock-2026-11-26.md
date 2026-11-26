# Phase 26 — FPR13 l01/l04 Owned 라이브 해제

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE26-FPR13-OWNED-LIVE-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | R-13FPR-GUI · phase25 · phase24 · FIG-03 |
| 대상 | `_check_fpr13_runner` live l01/l04 |
| 목적 | IDE bridge 없이 Owned chat/shell 증명으로 l01/l04 해제 |

## 1. 결론

l01/l04를 `_check_local_vibe_smoke`(IDE bridge)에서 떼어, live Owned 슬롯 Engine HELLO·shell 체크에 묶었다.  
`--include-live` 결과 **20/20 pass** (계약 16 + 라이브 4). selection·hermes·migration 미터치.

| id | 상태 | 근거 (measured) |
|---|---|---|
| l01_general_chat | **PASS** | `_check_owned_live_hello` exit 0 · `IRIS-ACF-HELLO` · slot `iris-agent.slot-e38f3ea761714c36` |
| l02_browser_gui | **PASS** | doctor.py (유지) |
| l03_process_gui | **PASS** | `_check_control_http_contract` (유지) |
| l04_shell_model | **PASS** | `_check_owned_live_shell` exit 0 · `shell.run` ok · marker · `tool_choice=required` |

증거: `.tmp/fpr13/results.json` · `.tmp/owned-live-hello/evidence.json` · `.tmp/owned-live-shell/evidence.json`.

## 2. 구조

```text
_check_fpr13_runner --include-live
  contract×16 → 기존 _check_* (offline)
  l01 → iris.system._check_owned_live_hello
          iris_agent_repo_dir(live) → owned slot
          Engine(InternalSidecar(.tmp/owned-live-hello)) + patch engine_python
          StatelessTurn → IRIS-ACF-HELLO
  l02 → doctor.py (unchanged)
  l03 → _check_control_http_contract (unchanged)
  l04 → iris.system._check_owned_live_shell
          same owned resolve + tool_choice=required
          host shell.run handler → echo marker
```

갈라짐: **l01/l04는 IDE/companion 경로를 쓰지 않음**. Owned chat/shell만 측정.

## 3. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 막지 못한 이유 / 비고 |
|---|---|---|
| `_check_fpr13_runner` SCENARIOS | l01→hello, l04→shell 모듈 교체 | 제목이 Owned 증명을 가리키게 맞춤 |
| `_check_owned_live_hello` | live resolve + HELLO | 신규. GUI 클릭 착지는 범위 밖 |
| `_check_owned_live_shell` | forced tool_choice + shell.run | fig-03 패턴. IDE vibe 경로 제거 |
| `_check_local_vibe_smoke` | 손대지 않음 | l01/l04에서 더 이상 호출하지 않음 |

하지 않은 일: selection 쓰기, hermes 삭제, migration 플래그, vibe_smoke/IDE bridge 수정.

## 4. 개선안

| 빈 자리 | 다음 |
|---|---|
| l02 | Wiki/Browser 실 GUI 클릭 경로 (제목 대비 약함 — phase25와 동일) |
| l03 | live process.manage + approval consume |
| GUI 한 턴 착지 | R-OWNED-PARITY / 선택 스모크 (이번 해제의 결정 증거 아님) |

## 5. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| `.tmp/fig03_min_repro.py` | HELLO·shell·tool_choice·python patch | 러너가 `iris.system._check_*`만 호출하는 계약 |
| phase24 post-cutover | live `iris_agent_repo_dir` + 격리 EngineHome | shell은 fig-03 쪽 |

## 6. 조치

1. R-13FPR-GUI → COMPLETE (라이브 4 pass · 계약 16 green).
2. phase25 BLOCKED 서술은 이 문서로 대체.
3. 커밋·push 없음.
