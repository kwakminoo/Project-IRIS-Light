# PHASE04 Shell Live Retest

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE04-SHELL-LIVE-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | wave1-F1 Speak coerce · ACF GUI 64k shell FAIL · IRIS native agent |
| 대상 | 격리 홈 `.tmp/acf-shell-live-retest` + Ollama `gpt-oss:20b` |
| 목적 | P0 shell 결함(모델 argv 형태 → Windows `cmd /c` exit 1)이 실모델 턴에서 닫혔는지 판정 |

## 1. 결론

**판정: PASS.** P0 shell 결함은 Speak 실행 경계에서 닫혔다. 격리 GUI에서 Speak 프로브(문자열 bash 리스트)와 실모델 `terminal` 호출(실제 JSON 배열 `cmd`) 모두 `command=echo MARKER`로 정규화된 뒤 `argv=["cmd","/c","echo MARKER"]` · **exit 0** · `ok:true`를 남겼다. live `~/.iris-light` 엔진 선택·`legacy_migration_approved`·commit/push·유료 API는 건드리지 않았다. 비서 본문이 마커를 인용하지 않고 octokit 할루시네이션으로 빗나간 것은 셸 결함과 별개의 soft 이슈다.

## 2. 확인한 사실

| # | 항목 | 값 | 근거 |
|---|---|---|---|
| 1 | 계약 검사 | PASS | `python -m iris.infrastructure._check_tool_contract` |
| 2 | Speak 프로브 입력 | `cmd="['bash','-lc','echo IRIS_SHELL_8A8B6CC50AEE']"` | `speak-coerce-probe.json` |
| 3 | Speak 정규화 | `command=echo IRIS_SHELL_8A8B6CC50AEE` | 동 파일 |
| 4 | Speak 실행 | ok · exit 0 · stdout 마커 | run `32a88fe8…` |
| 5 | 모델 도구 인자 | `cmd=["echo","IRIS_SHELL_8A8B6CC50AEE"]` (실배열) | `native-tool-results.jsonl` |
| 6 | 모델 실행 argv | `["cmd","/c","echo IRIS_SHELL_8A8B6CC50AEE"]` exit 0 | run `126305e3…` |
| 7 | TOOL 연계 | `terminal`→`shell.run` · `request_id=5b862e77…` · `tool_call_id=call_dw6jc7cm` · TOOL_RESULT ok=true | `turn_end_watch.log` / `acf-product/logs/agent.log` |
| 8 | Control 직호출 list | FAIL (Speak 정규화 없음, 설계상) | `gui-evidence.json` `control_list_ok:false` |
| 9 | 비서 본문 | 마커 미인용 · octokit 문구 | soft, non-P0 |
| 10 | live 엔진 선택 | 미변경 | 격리 `IRIS_AGENT_HOME=.tmp/acf-product`만 사용 |

마커: `IRIS_SHELL_8A8B6CC50AEE`  
증거: `.tmp/acf-shell-live-retest/gui-evidence.json`

## 3. Pass predicate

| 조건 | 결과 |
|---|---|
| Speak bash-list coerce → echo 마커 | PASS |
| Speak/Control 실행 exit 0 · 정상 argv | PASS |
| 모델 `terminal` → `shell.run` ok · exit 0 | PASS |
| TOOL_CALL / TOOL_RESULT 연계 | PASS |
| 비서 마커 인용 | FAIL (soft) |
| **종합 P0** | **PASS** |

## 4. 구조

```
chat.send (격리 GUI)
  → sidecar TOOL_CALL model_tool_name=terminal
  → Engine TOOL_ROUTE canonical=shell.run
  → SpeakTools.invoke
       → normalize_speak_invoke   ★분기 (cmd 별칭 · list/문자열 list → command)
       → Control shell.run → iris_shell → Execution Runtime
  → TOOL_RESULT ok + runs/*/meta.json argv
  → assistant 착지
```

이번 요청의 Speak `normalize_speak_invoke`에서 갈라진다. Control `/v1/invoke`는 이 분기를 타지 않는다.

## 5. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 요청을 막지 못한 이유 / 수정 |
|---|---|---|
| `normalize_speak_invoke` (wave1-F1) | 문자열 `['bash','-lc',…]` → script | 계약 PASS. 실모델은 **JSON 배열** `cmd`를 보냄 |
| 동 함수 (이번 수정 전) | 배열을 `str(list)`로 넣어 `['echo',…]` 문자열이 됨 | bash가 아니면 unwrap 실패 → `cmd /c "['echo',…]"` exit 1 |
| 동 함수 (이번 수정) | 실배열·문자열 list 모두 argv join / bash -lc unwrap | 모델 턴 exit 0 |
| SpeakTools.invoke | 정규화 후 validate·Control | 정상 |
| Control `/v1/invoke` | 정규화 없음 | list 직호출은 계속 FAIL (모델 경로 아님) |
| 비서 생성 | 도구 성공 후 본문 | 마커 인용 실패 — soft |

하지 않은 일: live 엔진 교체, migration 승격, Control HTTP에 Speak 정규화 이식, 비서 할루시네이션 프롬프트 수정.

## 6. 개선안

1. Control `/v1/invoke`에도 동일 `normalize_speak_invoke`를 넣을지 제품 계약으로 결정 (지금은 Speak-only).
2. 비서 soft 이탈은 별 티켓 (도구 성공 후 verbatim 강제).

## 7. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| `.tmp/acf_gui_forced_tools.py` | 격리 GUI·Control·chat.send 패턴 | 셸 전용으로 `.tmp/acf_shell_live_retest.py`에 축소 재사용 |
| wave1-F1 bash 문자열 coerce | `_coerce_list_literal_command` | 유지·확장만 |
| `subprocess.list2cmdline` | Windows argv join | stdlib |

## 8. 조치

1. Speak 경계에 실배열 `cmd` coerce 착지 (`speak_capability.py`).
2. `_check_tool_contract`에 배열·`['echo',…]` 문자열 케이스 추가.
3. 격리 재시험 증거 보존: `.tmp/acf-shell-live-retest/`.
4. live 홈·커밋·push 없음.
