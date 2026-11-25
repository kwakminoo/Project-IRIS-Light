# IRIS Agent Core Ownership Baseline (ACO-00)

| 항목 | 내용 |
|---|---|
| 문서 번호 | ACO-00 |
| 작성일 | 2026-11-25 |
| 관련 | Wave 1.2 Hotfix HEAD `d23f937`, PIN `a382af23` |
| 대상 | Reference Engine · Product Preservation · Live Turn |
| 목적 | 엔진 교체 전 기준선·하드 게이트 |

## 1. 결론

**판정: GO** — 엔진 probe READY, 실모델 턴 착지 증명, Product Preservation 자검 통과. ACO-P2(동결) 이후 착수 가능.

Wave 1.2 보고서의 `probe_engine_python → None = 미준비`는 **오판**이다. 코드 계약상 `None`은 에러 없음(준비됨)이다.

## 2. Reference Engine

| 항목 | 값 |
|---|---|
| Upstream | https://github.com/NousResearch/hermes-agent.git |
| PIN / installed HEAD | `a382af23f4c067d23463b5781958684c2cda82bc` |
| Checkout | `%USERPROFILE%\.iris-light\agent\hermes-agent` (레거시 폴더명) |
| Package | `hermes-agent` 0.0.0, MIT (Nous Research) — identity overlay 미완전 |
| Engine Python | `…\hermes-agent\venv\Scripts\python.exe` |
| Probe | `probe_engine_python` → `None` (READY), CLI=`hermes_cli` |
| Entry | `iris/engine/agent_entry.py` → `from run_agent import AIAgent` |
| Product path | `InternalSidecar` + `iris/engine/_sidecar_main.py` (기본 `:8642` 아님) |
| Provider (UI) | `api:…:nvidia/nemotron-3-ultra-550b-a55b` (`hermes_online` 토글과 무관, `agent_enabled=true`) |
| Config disk | `custom` / Ollama `http://127.0.0.1:11434/v1` / `gemma4:e2b` (디스크 기본; 세션은 API 모델 사용) |
| Tool contract | Sidecar가 Hermes builtin을 비우고 Iris SpeakTools만 노출 |
| Stream / done | stdout delta + Windows UDP terminal done/fail |

### Baseline overlays (`apply_iris_agent_baseline_overlays`)

1. ollama options guard  
2. stdio dead-check patch  
3. tool_choice overlay  
4. package identity overlay (`hermes-agent` → `iris-agent`)  
5. CLI rename overlay  
6. CLI shim overlay  
7. absorbed toolsets (terminal/browser 등) — sync/install 경로  

설치 트리에 `.iris-agent-baseline` stamp 없음 → overlay 재적용 여부는 P2 동결 시 소스 베이크로 흡수.

## 3. Live Turn (실측)

증거: `.iris_light_test_tmp/verify-iris/aco-p0/live_turn.json`

| 항목 | 결과 |
|---|---|
| send_ok | true |
| conversation_id | 394 |
| user_id → assistant_id | 1561 → 1562 |
| marker_in_reply | true (`ACO-P0-GATE-1795574233`) |
| land_db_ok | true |
| elapsed_sec | 7.654 |
| model | nvidia/nemotron-3-ultra-550b-a55b |

## 4. Product Preservation

| 항목 | 결과 | 근거 |
|---|---|---|
| 모델 피커 roster / sort | PASS | `python -m iris.ui.chat._check_model_picker_roster` |
| 채팅 착지 계약 | PASS | `python -m iris.ui._check_chat_landing_contract` |
| Sidecar-only 제품 경로 | PASS | `python -m iris.engine._check_iris_agent_sidecar_only` |
| 피커 TypeError / favorites Hotfix | 코드 기준선 | commits `72aad89`…`d23f937` |
| Shell Box / 스크롤 / H1 | 비수정 유지 | ACO 범위 밖 UI 미변경 |

## 5. Perf 기준선 (P7 허용 범위용)

| 지표 | 값 |
|---|---|
| 턴 완료 (marker echo) | 7.654 s |
| 비정상 종료 | 0 (이번 측정) |

P7에서 Reference vs Owned 비교 시 동일 모델·동일 프롬프트로 반복. 사후 완화 금지.

## 6. 조치

1. ACO-P1 Inventory · ACO-P2 Freeze 진행.  
2. Reference `hermes-agent` 설치는 컷오버 전까지 삭제하지 않음.  
3. 증거 디렉터리 `.iris_light_test_tmp/verify-iris/aco-p0/` 유지.
