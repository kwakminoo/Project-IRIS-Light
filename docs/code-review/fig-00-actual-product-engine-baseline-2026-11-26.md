# FIG-00 Actual Product and Engine Baseline

| 항목 | 내용 |
|---|---|
| 문서 번호 | FIG-00 |
| 작성일 | 2026-11-26 |
| 관련 | Wave 1 Final Integration & Release Gate |
| 대상 | 실행 중 IRIS Desktop · Reference/Owned Core |
| 목적 | 수정 전 실측 고정. Manifest 존재만으로 Owned 실행 판정 금지 |

## 1. 결론

현재 실 GUI는 **Reference Core(`hermes-agent`)** 위에서 돈다. Vendor Owned Core(`iris-agent-core` 0.1.1+iris.a382af23)는 저장소에 있으나 **live `iris-agent` checkout은 없다**. `legacy_migration_approved=false`. Git HEAD는 리뷰 기준 `64bf196`과 동일하고 working tree는 clean이다. Final Gate 기존 판정 NO-GO의 P0(모델 shell 리스트 문자열 → exit 1)는 여전히 열려 있다.

## 2. 확인한 사실

| 항목 | 값 | 판정 |
|---|---|---|
| Git HEAD | `64bf196826cfb858b7703ab879b65ea06503ac25` | measured |
| Branch | `main` (= `origin/main`) | measured |
| Working Tree | clean | measured |
| Desktop Python | `C:\Program Files\Python313\pythonw.exe -m iris` (PID 37432) | measured |
| Workspace venv | `…\Project-IRIS-Light-main\.venv` (WebEngine child) | measured |
| Agent Core Python | `~\.iris-light\agent\hermes-agent\venv\Scripts\python.exe` (3.14.7) | measured |
| AIAgent import | `…\hermes-agent\run_agent.py` → `run_agent.AIAgent` | measured |
| Engine package | `hermes-agent` version `0.0.0` (pyproject) | measured |
| Sidecar | `_sidecar_main.py` via hermes venv (PIDs 40484→30168, parent GUI 37432) | measured |
| Engine selection | live = hermes-agent; `iris-agent` root **없음** | measured |
| Reference vs Owned | Reference 실행 / Owned vendor만 존재 | measured |
| `probe_engine_python` | `None` (= **에러 없음**, 설치 probe 통과) | measured |
| `engine_python` | hermes-agent venv python | measured |
| SOURCE_MANIFEST | vendor `0.1.1+iris.a382af23`, `legacy_migration_approved: false` | measured |
| 현재 모델(config.yaml) | `provider: custom`, `model: gemma4:e2b`, `tool_choice: required` | measured |
| Context / 승인 / Workspace | config에 context·approval 키 일부만; 상세는 UNVERIFIED | partial |
| Tool Schema Fingerprint / 활성 Tool 수 | 이번 턴 미측정 | UNVERIFIED |
| 제품 UI 상태 | GUI 기동 중 (Home 추정); 화면 전수 미촬영 | EXISTING BUT UNVERIFIED |
| Agent Home 오염 | agent 루트에 사용자 `.py`/PDF 등 존재 | measured (삭제 안 함) |
| installs 슬롯 | `agent/installs/` 2개 존재 | measured |

## 3. 검증 수준 구분 (기존 보고서 교차)

| 수준 | 상태 |
|---|---|
| Source Implementation | Wave 1.3 Native Dispatcher·별칭·FinalizedStartPlan 등 코드 존재 (reports) |
| Unit/Contract | FPR-14 / FGC 계약 검사 다수 exit 0 주장 |
| Control API | shell/process 성공 증거 기록됨 |
| Actual Agent Turn | 20B/120B 부분; shell 모델 경로 exit 1 잔여 |
| Actual GUI | Shell Box Control 경로 증명; 모델 경로·전수 UNVERIFIED 잔여 |
| Clean Install / Cutover | 미실시 · migration false |

## 4. 조치

1. FIG-01 보존 표는 기존 FPR-00/14를 재사용하고 미검증만 갱신.
2. P0: 모델 `command`가 bash/argv 리스트 문자열일 때 Speak 경계 coerce + Windows terminal 설명 보강 (FIG-05).
3. Owned Core는 사용자 홈을 바꾸지 않고 격리 슬롯/테스트 홈에서만 비교 (FIG-02).
4. commit / push / legacy 승격 / 유료 확대 없음.
