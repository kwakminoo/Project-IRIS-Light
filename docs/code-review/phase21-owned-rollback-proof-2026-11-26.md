# PHASE 21 Owned Core install→activate→rollback 격리 증명

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE21-OWNED-ROLLBACK-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | PHASE 16 Owned Core 0.1.1 격리 설치 · `rollback_iris_agent` · residual recovery |
| 대상 | `.tmp/owned-rollback-proof/agent` 격리 EngineHome |
| 목적 | live `~/.iris-light` 없이 Owned Core 이중 슬롯 설치·선택 전환·롤백·양쪽 probe 증명 |

## 1. 결론

격리 홈 `.tmp/owned-rollback-proof/agent`에 `install_iris_agent_with_system_python`을 두 번(첫 설치 + `update=True`) 돌려 실 체크아웃 두 개를 만들었다. `rollback_iris_agent(home)` 후 selection이 previous로 뒤집혔고, active·previous 모두 `_probe_owned_slot` 통과했다. 두 슬롯은 디스크에 남았다. live `~/.iris-light/agent` selection·mtime·자식 목록은 전후 동일. `legacy_migration_approved` 미승격. **rollback_ok = true**.

## 2. 실측 표

| 필드 | 값 | 상태 |
|---|---|---|
| EngineHome | `…/.tmp/owned-rollback-proof/agent` | measured |
| install1 active | `iris-agent.slot-7f5cdb0df07b4c73` | measured |
| install2 active (before rollback) | `iris-agent.slot-657ee17c42b34fdd` | measured |
| previous before rollback | `iris-agent.slot-7f5cdb0df07b4c73` | measured |
| rollback returned | `iris-agent.slot-7f5cdb0df07b4c73` | measured |
| selection after | active=A, previous=B | measured |
| probe_active_ok | **true** (`iris-agent-core 0.1.1+iris.a382af23`) | measured |
| probe_previous_ok | **true** (동일) | measured |
| both slots on disk | **true** | measured |
| live_untouched | **true** | measured |
| live selection file | 없음 (전후) | measured |
| legacy_migration_approved 승격 | **false** | measured |
| evidence | `.tmp/owned-rollback-proof/evidence.json` | measured |
| runner | `.tmp/owned-rollback-proof/run_proof.py` | measured |

## 3. 구조

```
vendor/iris-agent-core
  → install_iris_agent_with_system_python(home=.tmp/…/agent, update=False)
       → slot-A materialize + uv sync + probe + _activate_staged
       → selection {active:A, previous:null}
  → install_iris_agent_with_system_python(home=…, update=True, model_check=noop)
       → slot-B materialize + uv sync + probe + _activate_staged
       → selection {active:B, previous:A}
  → rollback_iris_agent(home)
       → probe previous(A) → _write_engine_selection(A, B)
       → selection {active:A, previous:B}
  → _probe_owned_slot(A) / _probe_owned_slot(B)  둘 다 ok
  ✂ ~/.iris-light/agent   ← selection·mtime 미변경
```

갈라짐: 제품 live EngineHome과 격리 `.tmp/owned-rollback-proof`는 홈·selection·python이 다르다. 이번 unit은 격리 홈만.

## 4. 코드 리뷰

| 지점 | 이번 요청에서 한 일 | 막거나 통과한 이유 |
|---|---|---|
| `install_iris_agent_with_system_python(home=…)` | 격리 홈 첫 설치 | public API · live 비접촉 |
| `update=True` + `model_check=noop` | 두 번째 실 슬롯 생성 | update 경로는 model_check 필수. noop으로 게이트만 통과 |
| `_activate_staged` | install 내부에서 active/previous 기록 | selection JSON 형식의 정본 |
| `rollback_iris_agent` | previous probe 후 selection flip | 슬롯을 옮기지 않고 선택만 바꿈 |
| `_probe_owned_slot` | 롤백 후 active·previous 재검증 | copytree 슬롯은 venv 절대경로로 실패 → 이중 install로 우회 |
| live fingerprint | selection/children/mtime 전후 비교 | live 쓰기 없음 증명 |

하지 않은 일: live hermes 삭제·전환, `legacy_migration_approved=true`, commit/push, owned-core-011 파괴, 제품 트리에 `_check_*.py` 추가.

## 5. 개선안

구조상 빈 자리만:

1. copytree로 두 번째 슬롯을 싸게 만들면 Windows venv `sys.prefix`가 원본을 가리켜 `_probe_owned_slot`이 깨진다. 복구 증명에는 이중 install(또는 슬롯별 uv sync)이 필요하다.
2. `update=True`가 `model_check`를 강제한다. 격리 증명에서는 noop이 충분하나, 제품 경로에서는 실제 모델 검사가 남는다.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| `install_iris_agent_with_system_python` / `rollback_iris_agent` | public 설치·롤백 | 가져옴 |
| PHASE 16 owned-core-011 | 격리 home·evidence 패턴 | 파괴 대상으로는 재사용 안 함. 패턴만 참고 |
| `tests/test_iris_agent_install_rollback.py` | mock 롤백 계약 | 단위 mock. 이번은 실 uv sync 격리 증명 |
| live hermes-agent | — | 의존·삭제·전환 금지 |

## 7. 조치

1. 증거: `.tmp/owned-rollback-proof/evidence.json` (`rollback_ok: true`).
2. 재실행: `.venv\Scripts\python.exe .tmp\owned-rollback-proof\run_proof.py`.
3. blocker 없음. commit/push·live 엔진 작업은 하지 않음.
