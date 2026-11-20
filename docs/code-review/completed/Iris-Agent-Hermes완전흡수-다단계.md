# Iris Agent — Hermes 완전 흡수 다단계

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-11-19-AGENT-ABSORB |
| 작성일 | 2026-11-19 |
| 관련 | Phase1 process NO-GO, Phase5 Merge NO, tool-window unify, 일체화 갭 조사 |
| 대상 | 제품에서 Hermes 정체성·이중 런타임·공개 이름 제거 |
| 목적 | Iris가 독자 Agent로 보이·동작하도록 흡수. Iris는 계속 기동·착지 |

## 1. 무엇이 바뀌는가

제품 표면·운영·코드에서 Hermes를 찾을 수 없게 한다. 채팅은 이미 `InternalSidecar` + `run_turn`이다. 남는 Hermes는 `:8642` gateway ops, `hermes_*` 이름, 스킬/문서/UI, vendor 표기다.

### 도메인 형태 (고정)

```
IrisAgent (유일한 제품 정체성)
  home: ~/.iris-light/agent
  source: InternalSidecar only   # 자식 = Iris Agent Runtime
  speak: PHASE4 SpeakTools
  sync: sidecar/home 파일만. :8642 gateway 제품 경로 금지
  names: 제품 로직은 agent_* 만. thin hermes_* shim 삭제됨 (hermes_shims=0)
```

### 전제 공격

| 전제 | 판정 |
|---|---|
| 완전 흡수 = Qt에 AIAgent same-process | **거짓**. Phase1/5 NO. 크래시·venv 격리 포기 | 
| 완전 흡수 = Hermes 정체성·gateway 프로세스 제거 + Iris Runtime 소유 | **참**. 이 계획이 이걸 한다 |
| 채팅이 sidecar면 :8642는 죽음 | **거짓**. ops가 gateway를 살림 → PR-A가 죽인다 |

Qt same-process Merge는 이 흡수 범위 밖이다. 재논의는 Prove+이득 문서 후에만.

## 2. PR 착륙 순서

```
trunk
  ├─ PR-A  ops gateway 제거 (독립)
  ├─ PR-B  hermes_* 로직 → agent_* (PR-A 후 권장, 파일 겹치면 직렬)
  ├─ PR-C  스킬·문서·UI 문자열 (PR-B 후)
  └─ PR-D  vendor/홈 표기 + inventory 최종 green (PR-C 후)
```

| PR | 의존 | 만지는 주 파일 | 한 가지 변화 | 결과 | 검증 |
|---|---|---|---|---|---|
| PR-A | 없음 | `iris_agent_workers`, `iris_agent_control_sync`, `extension_install_worker`, `agent_turn`, `agent_runtime`, setup | 제품 ops가 `restart_hermes_gateway` / `:8642` 를 안 부른다 | sync·설치·확장이 sidecar/home만 | unit: 신규 `_check_no_product_gateway_ops`. live: Iris 기동 → ControlSync → 채팅 1턴. perf: n/a |
| PR-B | A | `hermes_tool_activity`→`agent_tool_activity`, settings aliases 축소, inventory | 제품 로직 `hermes_*` 모듈 0 (shim 제외) | inventory freeze PASS | unit: inventory freeze. live: 채팅 footer. review-gate: 공개 API 이름 |
| PR-C | B | `integrations/iris-skills`, UI 카피, setup 스텝 id | 사용자·에이전트 문구에 Hermes 브랜드 없음 | 스킬 경로 iris-agent | unit: 문자열 스캔 자검. live: 설정/setup 화면 |
| PR-D | C | pin/README, `hermes-agent` 체크아웃 표기, Phase5-merge 문서 | 문서·vendor가 Iris Agent Runtime만 말함 | ExternalGateway 문서 잔상 삭제 | unit: inventory+문서 마커. live: doctor |

각 PR 공통 회귀: `_check_iris_agent_sidecar_only`, `_check_hermes_required`(또는 후속 rename), `_check_chat_landing_contract`. 깨지면 버그픽스 PR을 끼워 넣고 재개.

## 3. 하지 않는 일

- Qt/`MainWindow`에 `AIAgent` import (Merge NO 유지)
- Hermes `file`/`terminal` toolset 재활성
- 사이드바 클릭을 모델 턴으로 강제

## 4. 진행 (2026-11-19)

| 단위 | 상태 |
|---|---|
| PR-A / 1b gateway ops | 완료 (제품 restart 0) |
| Unit0 inventory `agent_tool_activity` | 완료 |
| PR-B1–B3 API/settings | 완료 (Control `hermes_enabled` dual-key 잔여 제거됨 — `agent_enabled` only) |
| Unit7 thin hermes_* shim 삭제 | 완료 (`hermes_shims=0`, `hermes_modules=0`) |
| Unit4 product list_*/setup step/hero | 완료 (`list_agent_*`, `agent_runtime`/`agent_running`, hero AGENT=SIDECAR) |
| PR-C user brand | 완료 |
| PR-D vendor/skills path | 완료 (`skills/iris-agent` 정본 + legacy iris-control 마이그레이션, checkout alias, Phase5/serin docs) |
| PR-E checkout 설치 정본 `iris-agent` | 완료 (write=`iris-agent`, hermes→iris rename soft-fail, 심 축소) |
| Qt same-process | 범위 밖 (NO-GO 유지) |

## 5. 조치

1. 본 문서가 흡수 실행 체크리스트다.
2. 단위는 fresh `poteto-agent` + TDD. 메인 채팅은 재검증·조율만.
3. Iris 기동·착지가 깨지면 해당 단위를 멈추고 버그픽스 후 재개한다.
