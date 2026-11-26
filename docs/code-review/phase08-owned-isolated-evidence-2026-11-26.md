# PHASE 08 Owned Isolated Evidence

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE08-OWNED-ISO-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | PHASE 00 · FIG-02 · Owned Core canon · residual tracker U2 |
| 대상 | `.tmp/acf-clean` 격리 Owned fixture · vendor `iris-agent-core` |
| 목적 | live `~/.iris-light` hermes 없이 Owned fixture가 import·기동 가능한지 실측 갱신 |

## 1. 결론

격리 Owned fixture(`.tmp/acf-clean/iris-agent`)는 **live hermes checkout을 경로·모듈 의존으로 쓰지 않고** `run_agent.AIAgent`를 import한다. 패키지는 `iris-agent-core` editable 설치다. cheap 계약 검사 4종은 모두 PASS다.

vendor 정본(`0.1.1+iris.a382af23`)과 fixture 매니페스트(`0.1.0+iris.a382af23`)는 **revision은 같고 version/sha는 불일치**다. fixture는 구 스냅샷이다. `legacy_migration_approved`는 vendor만 `false`로 명시되어 있으며, 이번 측정에서 승격하지 않았다. live 엔진은 건드리지 않았다. Reference Core는 삭제하지 않았다.

## 2. 실측 표

| 필드 | 값 | 상태 |
|---|---|---|
| Owned fixture root | `…/Project-IRIS-Light-main/.tmp/acf-clean/iris-agent` | measured |
| Owned python | `…/.tmp/acf-clean/iris-agent/venv/Scripts/python.exe` | measured |
| AIAgent class | `run_agent.AIAgent` | measured |
| AIAgent file | `…/.tmp/acf-clean/iris-agent/run_agent.py` | measured |
| Dist package | `iris-agent-core` | measured |
| Dist version (fixture install) | `0.1.0+iris.a382af23` | measured |
| Dist install mode | editable (`.pth` → fixture root) | measured |
| Dist `hermes-agent` / `iris-agent` | PackageNotFoundError | measured |
| Fixture `SOURCE_MANIFEST.version` | `0.1.0+iris.a382af23` | measured |
| Fixture `upstream_revision` | `a382af23f4c067d23463b5781958684c2cda82bc` | measured |
| Fixture `legacy_migration_approved` | 키 없음 | measured |
| Vendor `SOURCE_MANIFEST.version` | `0.1.1+iris.a382af23` | measured |
| Vendor `upstream_revision` | `a382af23f4c067d23463b5781958684c2cda82bc` | measured |
| Vendor `legacy_migration_approved` | `false` | measured |
| Vendor ↔ fixture version match | **False** | measured |
| Vendor ↔ fixture revision match | True | measured |
| SHA mismatch keys | `pyproject.toml`, `uv.lock`; vendor-only `agent/inline_tool_executors.py`, `agent/tool_executor.py` | measured |
| Import `sys.path` live hermes | 없음 | measured |
| Import live module hits | 0 | measured |
| live `~/.iris-light/agent/hermes-agent` | 존재 (읽기만; 미사용) | measured |
| live `iris-agent` checkout | 없음 | measured |
| Prior HELLO evidence | `.tmp/acf-clean/turn-evidence.json` → `IRIS-ACF-HELLO` / 7.465s | existing |
| `tests.test_iris_owned_core_release` | 8 OK (0.178s) | measured |
| `iris.engine._check_agent_entry_owned` | `agent_entry owned boundary ok` | measured |
| `iris.system._check_iris_agent_owned_install` | `iris_agent_owned_install ok` + vendor path | measured |
| `iris.infrastructure._check_native_tool_hermes_disabled` | `ok blocked=apply_patch,clarify,patch` | measured |

## 3. 구조

요청(격리 Owned boot) 경로:

```
fixture venv python
  → editable iris-agent-core (.tmp/acf-clean/iris-agent)
    → run_agent.AIAgent
      → (in-tree) hermes_* 모듈명 잔존 · iris_agent_cli
  ✂ live ~/.iris-light/agent/hermes-agent   ← 이번 import에 미포함
```

갈라짐: **제품 live 경로**(Reference hermes)와 **격리 fixture 경로**(Owned)는 홈·python이 다르다. 이번 측정은 fixture만.

## 4. 코드 리뷰 (경로 지점)

| 지점 | 이번 증상에서 한 일 | 요청을 막지 못한/막은 이유 |
|---|---|---|
| fixture `venv` + editable dist | AIAgent를 fixture `run_agent.py`에서 로드 | live hermes path 불필요 (measured) |
| `SOURCE_MANIFEST` (fixture vs vendor) | revision 공유, version/sha 불일치 노출 | 설치 스냅샷 구버전; canon 승격 아님 |
| `agent_entry` / owned install checks | vendor·entry 경계 계약 PASS | product→Hermes 내부 바인딩 없음 확인 |
| native hermes disabled | apply_patch/clarify/patch 차단 확인 | Native Dispatcher 계약 유지 |
| in-tree `hermes_*` / `hermes_cli` | Owned 트리 안 모듈명·패키지 잔존 | **live 의존이 아님**. boot에 in-tree 동명 모듈은 로드됨 |
| `tools.web_tools` / `plugins.web` | import 경고만 | AIAgent 로드는 계속 성공 |

하지 않은 일: `legacy_migration_approved` 승격, live selection/engine 전환, Reference Core 삭제, commit/push, fixture를 vendor 0.1.1로 재설치.

## 5. Hermes residual (Owned fixture boot)

| 구분 | 판정 |
|---|---|
| live `~/.iris-light/.../hermes-agent` 필수 여부 | **아니오** (path/module hit 0) |
| in-tree `hermes_*` / `hermes_cli` / skills·스키마 이름 | **잔존** (non-venv 경로 약 88). fork 명명·호환 레이어 |
| PyPI/`hermes-agent` dist | fixture venv에 없음 |
| Boot에 실제로 로드된 in-tree 예 | `hermes_constants`, `hermes_logging`, `hermes_state`, `hermes_cli`, `hermes_bootstrap` → 전부 fixture 경로 |

## 6. 개선안

구조상 빈 자리만:

1. fixture를 vendor `0.1.1+iris.a382af23`로 **재 materialize**하면 version/sha 정합 증거를 닫을 수 있다 (승인·별도 unit).
2. in-tree `hermes_*` 동명 모듈은 미래 정본 정리 대상이다. 이번 boot 차단 요인은 아니다.
3. `plugins.web` 경고는 optional tool surface. Owned HELLO 경로와 분리해 추적.

## 7. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| 기존 `.tmp/acf-clean` fixture | venv·HELLO 증거 재사용 | 이미 존재·재설치 비용 불필요 |
| vendor `iris-agent-core` 0.1.1 | 정본 매니페스트/sha | fixture 갱신은 cutover 아님·별도 작업 |
| live hermes | 비교 Reference | 의존·전환 금지 계약 |

## 8. 조치

1. 이 문서를 U2(격리 Owned import/process 실측) 증거로 사용한다.
2. vendor↔fixture version gap은 다음 materialize unit에서만 닫는다.
3. Migration / live cutover는 `legacy_migration_approved=false` 유지로 계속 BLOCKED.
