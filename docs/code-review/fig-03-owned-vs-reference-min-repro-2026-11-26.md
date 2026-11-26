# FIG-03 Owned vs Reference 최소 재현

| 항목 | 내용 |
|---|---|
| 문서 번호 | FIG-03 |
| 작성일 | 2026-11-26 |
| 관련 | R-FIG-03 · FIG-02 · PHASE04 shell · owned-core-011 |
| 대상 | Owned `0.1.1` 격리 슬롯 · live `hermes-agent` python (읽기 전용) |
| 목적 | 동일 조건 HELLO + terminal→shell 1회 패리티 증거 |

## 1. 결론

Owned `0.1.1`과 Reference hermes는 격리 EngineHome + `gpt-oss:20b`에서 HELLO·shell 모두 통과했다. `hello_match=true`, `shell_match=true`. 첫 Owned shell은 도구를 안 타고 markdown bash로 마커를 지어냈다. 격리 홈에 제품과 같은 `agent.tool_choice: required`를 심고 terminal 함수명을 명시한 뒤 `shell.run` exit 0·marker_seen이 나왔다. live selection은 없었다. 증거: `.tmp/fig-03/evidence.json`.

## 2. 확인한 사실

| # | 항목 | 값 | 근거 |
|---|---|---|---|
| 1 | Owned python | `.tmp/owned-core-011/.../venv/Scripts/python.exe` | evidence meta |
| 2 | Owned HELLO | ok · `IRIS-ACF-HELLO` | `owned/hello/hello-evidence.json` |
| 3 | Reference HELLO | ok · `IRIS-ACF-HELLO` | `reference/hello/hello-evidence.json` |
| 4 | Owned shell (재시험) | ok · routed · `shell.run` exit 0 · marker | `owned/shell/shell-evidence.json` |
| 5 | Reference shell | ok · routed · `shell.run` exit 0 · marker | `reference/shell/shell-evidence.json` |
| 6 | 첫 Owned shell 실패 | `tool_calls=[]` · fenced bash 발명 · ~5s | 초기 evidence / agent.log Clean EOF |
| 7 | 강제 경로 | 격리 `config.yaml` `agent.tool_choice: required` | live agent 설정과 동일 레버 |
| 8 | live selection | 부재 유지 | before/after snapshot identical |
| 9 | Speak/Control GUI | 이번 최소 재현에 미사용 | host `bind_tool_handler`만 |

## 3. 구조

```
fig03_min_repro.py
  ├─ HELLO (무도구)
  │    Engine(InternalSidecar(home=.tmp/fig-03/{owned|reference}/hello))
  │      patch engine_python → Owned slot venv | live hermes venv
  │      StatelessTurn("Reply … IRIS-ACF-HELLO")
  │      → TurnFinished(text contains IRIS-ACF-HELLO)
  │
  └─ shell (terminal→shell.run)
       _seed_forced_tool_choice(home)  ★ agent.tool_choice=required
       Engine + bind_tool_handler(normalize_speak_invoke → cmd /c echo MARKER)
         StatelessTurn(speak_surface=home, prompt=call function tool terminal)
         sidecar TOOL_BIND terminal→shell.run
         model TOOL_CALL terminal
         host TOOL_ROUTE → handler → cmd /c echo MARKER
         TOOL_RESULT ok → TurnFinished(marker)
```

갈라지는 지점: **python 경로**(Owned 슬롯 vs live hermes). 실패 분기: 격리 홈에 `tool_choice`가 없으면 gpt-oss가 도구 없이 bash fence를 출력할 수 있다.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 요청을 막지 못한 이유 / 수정 |
|---|---|---|
| 격리 EngineHome `config.yaml` | 기본 없음 → `tool_choice` auto | 모델이 도구 스킵·발명. `required` 시드 추가 |
| `apply_tool_choice` (agent overlay) | live/hermes·owned 모두 배선됨 | 설정값이 auto면 강제 없음 |
| `Engine.bind_tool_handler` | shell.run 정규화 후 `cmd /c` | GUI 없이 host 왕복 증명 |
| `_install_iris_engine_tools` | terminal→shell.run TOOL_BIND | 양쪽 바인딩 존재. 실패 원인은 바인딩 아님 |
| `normalize_speak_invoke` | cmd/command → canonical | Speak 경계와 동일 |
| 약한 프롬프트 (`MUST call terminal`) | 모델이 fence로 흉내 | 함수명·command= 명시 + tool_choice |
| phase04 `run_everything` approval | GUI Speak 경로용 | fig03은 host handler라 approval 불필요 |
| live selection API | 호출하지 않음 | selection 파일 없음 유지 |

하지 않은 일: live hermes 삭제·cutover·`legacy_migration_approved`·GUI Control 전체·120B 유료 턴.

## 5. 개선안

1. FIG 재현 레버는 격리 홈에 `tool_choice: required`를 기본으로 심는다 (제품 live와 동일).
2. Owned `tool_search` core-visible 차이(0 vs 16)는 별도 FIG. 이번 shell은 Iris bind 이후 경로로 통과.
3. `--owned-shell-only`로 Owned만 재시험·evidence merge.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| live `agent/config.yaml` `tool_choice: required` | 격리 홈에 동일 키만 시드 | live 파일은 읽기만·쓰기 금지 |
| `.tmp/acf_shell_live_retest.py` | marker·terminal 강제 의도 | GUI/Control·run_everything 전체는 범위 밖 |
| `.tmp/acf_live_engine.py` | HELLO Engine+python patch | 레버에 이미 흡수 |
| `iris.system.iris_agent_tool_choice` | 제품 overlay·required 의미 | live `set_hermes_tool_choice`는 호출하지 않음 |
| OpenAI tool_choice API | 새 프레임워크 | 기존 agent overlay만 사용 |

## 7. 조치

1. 증거: `.tmp/fig-03/evidence.json` (`owned.shell_ok` · `parity.shell_match`)
2. 레버: `.tmp/fig03_min_repro.py` (`--owned-shell-only`, `_seed_forced_tool_choice`)
3. R-FIG-03 Gate C/E 최소 증거로 이 문서·JSON을 붙인다
4. live selection / hermes 삭제 / migration 승격 금지 유지
