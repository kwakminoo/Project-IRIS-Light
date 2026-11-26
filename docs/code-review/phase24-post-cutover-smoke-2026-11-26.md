# PHASE24 Post-cutover Owned 스모크

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE24-SMOKE-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | FIG-36 · PHASE22 · FIG-03 |
| 대상 | live `~/.iris-light/agent` resolve + Owned slot venv HELLO |
| 목적 | cutover 후 제품 경로가 Owned 슬롯을 쓰는지 headless로 증명 |

## 1. 결론

**통과.** live `iris_agent_repo_dir()`는 `iris-agent.slot-e38f3ea761714c36`을 반환하고, 그 슬롯 venv로 `InternalSidecar` HELLO가 `IRIS-ACF-HELLO`로 끝났다. selection·hermes·migration 플래그는 건드리지 않았다. 증거: `.tmp/post-cutover-smoke/evidence.json`.

## 2. 확인한 사실

| # | 항목 | 값 |
|---|---|---|
| 1 | `hello_ok` | true |
| 2 | `resolved_checkout` | `iris-agent.slot-e38f3ea761714c36` |
| 3 | selection.active / previous | Owned slot / `hermes-agent` (유지) |
| 4 | HELLO terminal | `TurnFinished(text='IRIS-ACF-HELLO')` · ~20.9s |
| 5 | `selection_untouched` | true |
| 6 | `blockers` | `[]` |

## 3. 구조

```
iris_agent_repo_dir(live home)
  → selection.active = iris-agent.slot-e38f3ea761714c36

Engine(InternalSidecar(EngineHome(.tmp/post-cutover-smoke/hello-home)))
  + patch engine_python → live owned slot venv
  → StatelessTurn("… IRIS-ACF-HELLO")
  → TurnFinished(text contains IRIS-ACF-HELLO)
```

갈라짐: **python = live Owned 슬롯**. 격리 EngineHome만 써서 사용자 DB를 건드리지 않음 (FIG-03과 동일).

## 4. 코드 리뷰

| 지점 | 한 일 | 비고 |
|---|---|---|
| `iris_agent_repo_dir` | live resolve 실측 | selection.active → Owned |
| `Engine` + `InternalSidecar` | kill_on_shutdown temp home | DB 오염 없음 |
| fig-03 HELLO 패턴 | patch `engine_python` | live 홈 쓰기 없음 |

하지 않은 일: selection 변경, hermes 삭제, migration 승격, GUI 클릭 착지, commit.

## 5. 개선안

구조상 GUI 한 턴 착지는 별도 단위로 남길 수 있다. 이번 스모크의 결정 증거(Owned resolve + 동일 python HELLO)는 headless로 충족했다.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져옴 |
|---|---|---|
| `.tmp/fig03_min_repro.py` | HELLO + python patch | shell/tool_choice |
| FIG-03 evidence 형식 | hello_ok · blockers | parity matrix |

## 7. 조치

1. 증거 `.tmp/post-cutover-smoke/evidence.json` 유지.
2. FIG-36 잔여 OPEN의 cutover 스모크를 PASS로 갱신.
3. selection / hermes / migration 금지 유지.
