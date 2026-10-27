# Iris Agent 홈·기억 정본 (Phase 4)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-HOME-P4 |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Hermes기반-구현경로.md` §4 4단계, §10.1 |
| 대상 | 제품 홈·레거시 마이그레이션·채팅 정본·supervisor 갭 |
| 목적 | 배포·기억을 한 제품 경로로 묶고 소유권 게이트를 갱신 |

## 1. 결론

활성 런타임 홈은 `IRIS_AGENT_HOME` 또는 `~/.iris-light/agent` 만이다.  
`%LOCALAPPDATA%\hermes` 는 복사 마이그레이션 원본이며 활성 쓰기에 쓰지 않는다.  
사용자 보이 채팅 정본은 Iris SQLite `chat_messages` 다.  
supervisor( HealthWorker / setup / login warm)는 Phase 4b에서 **CLOSED**.  
`ensure_iris_agent_runtime` 참고: `Iris-Agent-supervisor-Phase4b.md`.

## 2. 확인한 사실

| 사실 | 근거 |
|---|---|
| install/update 가 `load_pinned_sha()` 사용 | `hermes_install` / `hermes_update` 소스 |
| Phase 1 `iris_agent_home` 이 레거시 폴백 | 구 `agent_runtime.py` |
| UI가 `chat_messages` 기록 | `ChatSession` → `conversations.append_message` |
| HealthWorker·setup·warm 분산 | `main_window` + workers |

## 3. 구조

```
Iris 기동 / 설치 / gateway ensure
  └─ ensure_iris_agent_home()
         ├─ migrate_legacy_agent_home (copy .env·config·memories·skills)
         └─ product_agent_home()  ← 유일한 활성 홈
                └─ hermes_home() / install / gateway / sync / warm

채팅 UI
  └─ ChatSession.record
         └─ Iris SQLite chat_messages   ← 정본
  (별도) Agent session DB               ← 루프 ephemeral, UI 아님
```

## 4. 코드 리뷰

| 지점 | 이번 역할 | 막지 못한/남긴 것 |
|---|---|---|
| `agent_runtime.iris_agent_home` | 레거시 폴백 제거 | — |
| `migrate_legacy_agent_home` | 멱등 copy-then-stamp | 원본 삭제는 안 함 (안전) |
| `ensure_hermes_gateway_running` | 홈 ensure 호출 | Health/setup/warm 합류는 안 함 |
| `chat_canonical` | 정본 표·상수 | 세션 DB 삭제 아님 |
| `api_quota` 등 하드코딩 홈 | `hermes_home()` 로 통일 | setup_protocol 로그 문구 일부 잔존 |

하지 않은 일: Phase 5 in-process, 새 `hermes_*` 모듈, HealthWorker 프레임워크 재작성.

## 5. 개선안 (빈자리)

1. ~~supervisor: setup + HealthWorker + login warm → 한 ensure 진입~~ → Phase 4b CLOSED.
2. ~~setup_protocol 사용자 로그 `%LOCALAPPDATA%\hermes` 문자열 제거~~ → Phase 4b.
3. 마이그레이션 후 레거시 읽기전용 보관 정책(또는 사용자 확인 후 삭제) UX.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| XDG Base Directory | 제품 홈 `~/.iris-light/agent` | 이미 채택 |
| rsync --ignore-existing | 대상 존재 시 skip | stdlib `copy2`/`copytree` 로 충분 |
| systemd-style oneshot migrate | stamp 파일 | `.iris-agent-migrated-from` 로 최소 구현 |

## 7. §10.1 게이트 (Phase 4 종료 시점)

| # | 게이트 | 상태 |
|---|---|---|
| 1 | 툴 registry 포크 소유 | **부분** (Phase 2.x native wiki 등. 147 MCP 전부 제거 아님) |
| 2 | 설정 생성권 Iris | **CLOSED** (Phase 3 필드 삭제) |
| 3 | 대화 정본 하나 | **CLOSED** (`chat_canonical` = Iris SQLite) |
| 4 | supervisor 하나 | **CLOSED** (Phase 4b `ensure_iris_agent_runtime`) |

일체화 완료 주장: **불가**. 게이트 1 잔여.

## 8. 조치

1. 자검: `.venv\Scripts\python.exe -m iris.system._check_iris_agent_home_phase4`
2. 병행: `_check_iris_agent_runtime_phase1`
3. 실기기: 레거시 홈 있으면 기동 후 `~/.iris-light/agent` 에 `.env`/stamp 확인
