# Iris Agent supervisor (Phase 4b / §10.1 gate 4)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-SUP-P4B |
| 작성일 | 2026-10-27 |
| 관련 | `Iris-Agent-Hermes기반-구현경로.md` §10.1 gate 4, Phase4 home §5 |
| 대상 | setup / HealthWorker / login warm 수명 ensure |
| 목적 | supervisor 한 진입으로 런타임 기동 소유권을 닫는다 |

## 1. 결론

`ensure_iris_agent_runtime` 하나가 home → provider → gateway ensure 를 소유한다.  
setup warm/step, `HermesHealthWorker`, `hermes_login_warm_cli` 가 이 심볼을 통한다.  
수명 정책은 **keep-background** (Iris 종료 후에도 gateway 유지 가능. login warm이 그 전제).  
§10.1 gate 4 = **CLOSED**. gate 1은 여전히 **부분**이므로 일체화 완료 주장은 하지 않는다.

## 2. 확인한 사실

| 사실 | 근거 |
|---|---|
| Phase 4 홈 ensure 만 gateway에 묶여 있었음 | `ensure_hermes_gateway_running` → `ensure_iris_agent_home` |
| Health/setup/warm 이 각자 gateway ensure 호출 | workers / setup_protocol / login_warm_cli |
| 게이트웨이 로그 실제 경로 | `hermes_home()/logs/iris-gateway` = 제품 홈 |

## 3. 구조

```
setup (_warm_core / _step_hermes_gateway)
HermesHealthWorker.run
hermes_login_warm_cli.main
        │
        ▼
ensure_iris_agent_runtime   ← supervisor (agent_runtime.py)
        ├─ ensure_iris_agent_home()
        ├─ ensure_hermes_provider_config()   (optional)
        └─ ensure_hermes_gateway_running()  (optional; restart 경로는 home+provider만)
                └─ gateway 자식 프로세스

Lifetime: keep-background
  Iris quit ≠ gateway stop
```

## 4. 코드 리뷰

| 지점 | 이번 역할 | 막지 못한/남긴 것 |
|---|---|---|
| `agent_runtime.ensure_iris_agent_runtime` | 공개 supervisor + 결과 dataclass | Phase 5 in-process 아님 |
| `HermesHealthWorker.run` | provider/ensure → supervisor | restart/MCP sync 자체는 워커에 잔류 |
| `setup_protocol` | warm·step start → supervisor; 레거시 로그 문구 제거 | 심볼명 `hermes_*` 잔존 |
| `hermes_login_warm_cli` | gateway ensure → supervisor | 파일명 hermes 유지 (모듈 신설 금지) |

하지 않은 일: 새 `hermes_*` 모듈, HermesClient 전면 rename, Phase 5 병합, gate 1 MCP 전량 native.

## 5. 개선안 (빈자리)

1. gate 1: Control MCP 잔여 툴을 포크 native registry로 더 옮긴다.
2. restart 경로도 supervisor 플래그(`mode=restart`)로 흡수할지 검토 (지금은 home+provider 후 restart 직접).
3. UI/스킬 사용자 문자열 Hermes 잔여 (§10.3).

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| systemd Oneshot+RemainAfterExit | keep-background 수명 비유 | Windows 작업 스케줄러 warm 이미 있음 |
| k8s sidecar co-terminate | Iris=앱, gateway=사이드카 | 제품 정책이 keep-background |
| supervisor 패턴 (Erlang) | 한 ensure 진입 | 프로세스 트리 재작성은 Phase 5 영역 |

## 7. §10.1 게이트 (Phase 4b 종료)

| # | 게이트 | 상태 |
|---|---|---|
| 1 | 툴 registry 포크 소유 | **부분** |
| 2 | 설정 생성권 Iris | **CLOSED** |
| 3 | 대화 정본 하나 | **CLOSED** |
| 4 | supervisor 하나 | **CLOSED** |

일체화 완료 주장: **불가** (gate 1 잔여).

## 8. 조치

1. `.venv\Scripts\python.exe -m iris.system._check_iris_agent_supervisor_phase4b`
2. 병행: home_phase4 / runtime_phase1 / settings_phase3 / hermes_required
