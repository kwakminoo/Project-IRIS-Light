# PHASE 00 Live Product Baseline

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE-00 |
| 작성일 | 2026-11-26 |
| 관련 | IRIS native independence · Hermes absorption |
| 대상 | 로컬 워크스페이스 + `~/.iris-light` 실측 (수정 없음) |
| 목적 | Owned Core 이관 전 제품 기준선 고정. FIG/FGC는 입력만, 라이브 증거 우선 |

## 1. 결론

이번 세션 실측 기준, **실행 Engine은 여전히 Reference Core(`hermes-agent`)** 이다. Vendor Owned Core(`iris-agent-core` `0.1.1+iris.a382af23`)는 저장소에 있으나 **live `iris-agent` checkout은 없다**. `legacy_migration_approved=false`. GUI 프로세스는 **이 측정 시점에 미기동**이라 데스크톱 PID 샘플은 BLOCKED이고, 런처 설계상 Desktop Python은 `C:\Program Files\Python313\pythonw.exe -m iris`로 해석된다. Tool schema fingerprint는 이번 턴 UNVERIFIED. 사용자 데이터·엔진 선택·마이그레이션 승격·commit/push·유료 API는 건드리지 않았다.

FIG-00(`64bf196`, GUI 기동 중)과 비교하면 **HEAD가 `47c1d21`로 전진**했고, **Reference 실행 / Owned 미착지 / migration false** 골격은 같다.

## 2. 확인한 사실 (compact)

| # | 항목 | 값 | 판정 |
|---|---|---|---|
| 1 | git HEAD / branch / dirty | `47c1d217d3b3fd9aa7a8a049040d024204e580a9` · `main` (=`origin/main`) · clean | PASS |
| 2 | Desktop Python / 실행 방식 | 런처: `dist/IRIS.exe` → `resolve_gui_pythonw` → `C:\Program Files\Python313\pythonw.exe -m iris` (바로가기 Target=`dist\IRIS.exe`). **라이브 GUI PID 샘플 0** | PARTIAL |
| 3 | Agent Core Python | `~\.iris-light\agent\hermes-agent\venv\Scripts\python.exe` (3.14.7). `probe_engine_python`=`None`(probe 통과). `engine_python`=동 경로 | PASS |
| 4 | AIAgent import | `~\.iris-light\agent\hermes-agent\run_agent.py` → `run_agent.AIAgent` (**Reference**, Owned 아님) | FAIL |
| 5 | Sidecar | 소스 `iris/engine/_sidecar_main.py` 존재. **Iris 자식 sidecar PID 없음** (GUI 미기동) | PARTIAL |
| 6 | Reference vs Owned install | live=`hermes-agent` 있음 / `iris-agent` **없음**. vendor=`vendor/iris-agent-core`(+runtime PIN/overlays). `vendor/hermes-agent` 없음. installs 슬롯 2개(`9c13b621…`, `ca9496a0…`) | FAIL |
| 7 | Engine selection / SOURCE_MANIFEST / migration | live selection=`hermes-agent`. Manifest=`vendor/iris-agent-core/SOURCE_MANIFEST.json` version `0.1.1+iris.a382af23`, `legacy_migration_approved: false`. PIN=`a382af23…` | PASS |
| 8 | Tool schema fingerprint | 라이브 바인딩 미계산 (에이전트 기동·유료 경로 회피) | UNVERIFIED |
| 9 | Model / provider (redacted) | `provider: custom`, `model/default: gemma4:e2b`, `base_url: http://127.0.0.1:11434/v1`, `agent.tool_choice: required`, api_key=`[REDACTED]` | PASS |
| 10 | User home / data paths | `C:\Users\kwakm\.iris-light` · agent=`…\agent` · db=`…\iris_light.db` · workspace venv=`.venv` (3.13.7) | PASS |
| 11 | Install/update/recovery → external Hermes | `agent_runtime.IRIS_AGENT_UPSTREAM_URL` / vendor `UPSTREAM` = `https://github.com/NousResearch/hermes-agent.git`. `iris_agent_install.py` hermes-agent·legacy_migration·fetch 경로 잔존. update는 Owned manifest 전제 | FAIL |
| 12 | Hard-dep callers (`hermes-agent` / `:8642` / gateway) | `iris`+`scripts` 파일 스캔: `hermes-agent` 18 · `:8642` 38 · `NousResearch/hermes-agent` 3. 대표: `agent_runtime.py`, `iris_agent_gateway.py`, `setup_protocol.py`, workers/checks | FAIL |

판정 기준: PASS=이번 세션 라이브로 고정 · FAIL=독립 Owned 목표에 반하는 실측 · PARTIAL=일부만 · UNVERIFIED=미측정 · BLOCKED=관측 불가. #2의 라이브 PID만 BLOCKED에 가깝고, 표에는 런처 증거와 합쳐 PARTIAL로 둔다.

## 3. 구조 (요청 경로)

```
Desktop IRIS.lnk
  → dist/IRIS.exe (thin launcher)
    → Program Files/Python313/pythonw.exe -m iris   [설계 실측; 이번엔 프로세스 없음]
      → EngineHome ~/.iris-light/agent
        → checkout: hermes-agent (Reference)  ★분기
        → (없음) iris-agent (Owned)
      → engine_python = hermes-agent/venv/python.exe
      → _sidecar_main.py  (소스만; 자식 PID 없음)
Vendor Owned: vendor/iris-agent-core + SOURCE_MANIFEST (migration false)
Upstream pin: vendor/iris-agent-runtime/UPSTREAM → NousResearch/hermes-agent.git
```

## 4. 코드 리뷰 (경로上 지점)

| 지점 | 이번 증상/기준선에서 한 일 | 독립성을 막지 못한 이유 |
|---|---|---|
| `IRIS_launcher` / `gui_python.resolve_gui_pythonw` | Desktop을 base `pythonw`로 고정 | 정상. Engine checkout과는 무관 |
| `probe_engine_python` / `engine_python` | hermes venv를 유효 설치로 인정 | Reference가 probe를 통과해 Owned로 안 넘어감 |
| `agent_runtime` checkout 해석 | `iris-agent` 우선·없으면 `hermes-agent` | live iris-agent 부재 → 레거시 유지 |
| `SOURCE_MANIFEST` + `legacy_migration_approved` | vendor Owned만 false로 존재 | 승격 없이 Reference 교체 금지 계약이 동작 중 |
| `_sidecar_main` | 제품 sidecar 진입 존재 | GUI 미기동으로 런타임 착지 미관측 |
| `iris_agent_install` / `UPSTREAM` | 외부 hermes git URL·legacy 가드 | 설치/복구가 여전히 upstream Hermes에 묶임 |
| `:8642` / gateway 호출부 | 주석·체크·compat 필드에 다수 잔존 | 제품 핫패스는 sidecar라고 해도 문자열·기본 URL hard-dep 남음 |

하지 않은 일: 사용자 홈 수정, migration 승격, 엔진 선택 변경, fingerprint 강제 계산, commit/push, 유료 API.

## 5. 개선안 (구조 빈자리만)

1. live `iris-agent` checkout + Owned venv를 Reference와 **격리 슬롯에서만** 비교 기동.
2. Desktop GUI 기동 후 sidecar parent PID·AIAgent 모듈 경로 재측정 (이번 BLOCKED/PARTIAL 해소).
3. Tool schema fingerprint를 오프라인/로컬 전용으로 고정하는 측정 훅.
4. install/update/recovery에서 `NousResearch/hermes-agent.git` 필수 경로 제거 또는 vendor-only.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| FIG-00 필드표 | 행 이름·판정 열 | 값 재사용 금지 — HEAD/GUI 상태가 달라짐 |
| vendor `iris-agent-core` | Owned 소스·manifest | live 교체·migration 승격 금지 |
| Hermes upstream git | — | 외부 의존 제거 대상. 이번 측정만 |
| 찾지 못함 | 오프라인 schema fingerprint 단일 CLI | 바인딩 헬퍼가 라이브 전제라 값 미산출 |

## 7. 조치

1. PHASE 이후 작업은 이 표의 FAIL/PARTIAL/UNVERIFIED만 갱신한다.
2. GUI 재기동 뒤 #2·#5·#8을 재실측한다.
3. Owned cutover 전 `legacy_migration_approved`는 false 유지.
4. 이 문서는 입력 증거. 코드/홈 변경 없음.
