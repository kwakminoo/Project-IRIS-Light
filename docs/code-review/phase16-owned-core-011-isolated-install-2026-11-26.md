# PHASE 16 Owned Core 0.1.1 격리 설치

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE16-OWNED-011-ISO-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | PHASE 08 · FIG-02 · vendor `iris-agent-core` · residual U2 |
| 대상 | `.tmp/owned-core-011/agent` 격리 EngineHome · vendor `0.1.1+iris.a382af23` |
| 목적 | live Hermes 없이 Owned Core 설치·import/boot 증명 |

## 1. 결론

격리 홈 `.tmp/owned-core-011/agent`에 `install_iris_agent_with_system_python(home=…, update=False)`로 vendor Owned Core `0.1.1+iris.a382af23`를 설치했다. `SOURCE_MANIFEST.version`·`pyproject.toml`/`uv.lock` sha256이 vendor와 일치한다. checkout venv에서 `run_agent.AIAgent` import가 성공했고, `sys.path`·로드 모듈에 live `%USERPROFILE%\.iris-light\agent\hermes-agent`가 없다. 계약 검사 4종 exit 0. `legacy_migration_approved`는 false 유지. live selection·hermes-agent는 미변경. `.tmp/acf-clean`은 stale로 남기고 새 canon은 `.tmp/owned-core-011`이다.

## 2. 실측 표

| 필드 | 값 | 상태 |
|---|---|---|
| EngineHome | `…/.tmp/owned-core-011/agent` | measured |
| active slot | `iris-agent.slot-2b7026c7c26c4dff` | measured |
| checkout `SOURCE_MANIFEST.version` | `0.1.1+iris.a382af23` | measured |
| vendor version | `0.1.1+iris.a382af23` | measured |
| version match | **True** | measured |
| upstream_revision | `a382af23f4c067d23463b5781958684c2cda82bc` | measured |
| package | `iris-agent-core` | measured |
| sha256 `pyproject.toml` | vendor ↔ checkout 일치 | measured |
| sha256 `uv.lock` | vendor ↔ checkout 일치 | measured |
| `legacy_migration_approved` | `false` (미승격) | measured |
| import `run_agent.AIAgent` | ok | measured |
| dist version | `0.1.1+iris.a382af23` | measured |
| `live_hermes_on_sys_path` | **false** | measured |
| module live hermes hits | 0 | measured |
| live `~/.iris-light` selection | 미기록/미변경 | measured |
| `tests.test_iris_owned_core_release` | 8 OK, exit 0 | measured |
| `iris.engine._check_agent_entry_owned` | exit 0 | measured |
| `iris.system._check_iris_agent_owned_install` | exit 0 | measured |
| `iris.infrastructure._check_native_tool_hermes_disabled` | exit 0 | measured |
| evidence JSON | `.tmp/owned-core-011/evidence.json` | measured |
| acf-clean | stale (`STALE-NOTE.md`) | chosen |

## 3. 구조

```
vendor/iris-agent-core (0.1.1+iris.a382af23)
  → install_iris_agent_with_system_python(home=.tmp/owned-core-011/agent)
    → _materialize_owned_core(staging)
    → uv sync --locked
    → _probe_owned_slot (AIAgent + sidecar hello)
    → _activate_staged → iris-engine-selection.json (격리 홈만)
  → checkout venv python -I
    → run_agent.AIAgent
  ✂ ~/.iris-light/agent/hermes-agent   ← import 경로에 없음
  ✂ live engine selection             ← 미기록
```

갈라짐: 제품 live EngineHome과 격리 `.tmp/owned-core-011`은 홈·selection·python이 다르다. 이번 unit은 격리 홈만.

## 4. 코드 리뷰

| 지점 | 이번 증상/요청에서 한 일 | 요청을 막지 못한/막은 이유 |
|---|---|---|
| `install_iris_agent_with_system_python(home=…)` | 빈 격리 홈에 Owned 설치 | fresh home → hermes 무매니페스트 게이트 미발동 |
| `legacy_migration_approved` | false 유지, 인자로 승격 안 함 | 계약대로 Reference 교체 금지 |
| `_materialize_owned_core` | vendor → slot 복사·sha 검증 | version/sha 정합 닫음 |
| `_finish_staged_install` / `_probe_owned_slot` | uv sync + AIAgent import + sidecar hello | live Hermes 없이 boot 증명 |
| `_write_engine_selection` | 격리 `home`에만 기록 | live `~/.iris-light` 비접촉 |
| `.tmp/acf-clean` | rematerialize 생략, STALE 노트 | 새 home을 canon으로 선택 (비용·이중 설치 회피) |

하지 않은 일: live hermes 삭제, live selection 전환, `legacy_migration_approved=true`, commit/push, acf-clean 재설치.

## 5. 개선안

구조상 빈 자리만:

1. 슬롯 이름이 `iris-agent.slot-*`로 남아 canonical `iris-agent` rename이 없다. 격리 증거에는 충분하나, 제품 UX/경로 가정은 selection 파일을 읽어야 한다.
2. `plugins.web` 미설치 경고는 optional surface. AIAgent import는 성공한다.
3. acf-clean HELLO 증거를 0.1.1에서 재측정하려면 별도 unit에서 rematerialize가 필요하다.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| vendor `iris-agent-core` 0.1.1 | 정본 트리·매니페스트·lock | 가져옴 (materialize 원본) |
| `install_iris_agent_with_system_python` | 격리 home 설치 경로 | 제품 기본 API 그대로 |
| `.tmp/acf-clean` fixture | — | stale; 새 home이 canon |
| live hermes-agent | — | 의존·삭제·전환 금지 |

## 7. 조치

1. 증거: `.tmp/owned-core-011/evidence.json` (version_match True, import_ok True, live_hermes_on_sys_path false).
2. 계약 검사 4종 exit 0 로그: `.tmp/owned-core-011/check-*.txt`.
3. acf-clean: `.tmp/acf-clean/STALE-NOTE.md`.
4. blocker 없음. commit/push·live 엔진 작업은 하지 않음.
