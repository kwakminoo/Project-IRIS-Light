# GPT-OSS ACF GUI 테스트 종합

| 항목 | 내용 |
|---|---|
| 문서 번호 | GPT-OSS-ACF-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | Final Gate Closure 3단 · ACF GUI 64k · Owned Host tool path |
| 대상 | 모델 `gpt-oss:20b` (Ollama `http://127.0.0.1:11434/v1`) |
| 목적 | 이번 GPT-OSS 라이브 테스트의 인자·로그·결과·판정을 한곳에 모음 |

## 1. 결론

디스크에 남은 증거는 **`gpt-oss:20b`** 다. 요청 문구의 `12b`와 일치하는 `gpt-oss:12b` 실행 기록은 없다. 같은 `agent.log` 스트림에 **`gemma4:12b` 한 턴**(2026-11-25 23:03)만 섞여 있다.

판정은 Final Gate Closure와 같다. **Product Stability NO-GO.**

| 구분 | 결과 | 근거 |
|---|---|---|
| 텍스트 턴 (ACF-HELLO) | PASS | Owned/Reference 모두 `TurnFinished(text='IRIS-ACF-HELLO')` |
| Host 도구 라우팅 | PASS | `terminal → shell.run owner=iris`, `browser_open → browser.open owner=iris` |
| Control 직호출 shell/navigate/open+url | PASS | retest `control_*_ok: true` |
| 모델 `browser_open` + `url` (스키마 별칭 후) | PASS | `ok: true`, 소요 36.59s |
| 모델 `shell.run` (강제 재시험) | FAIL | `exit 1 · fail`. 모델이 `cmd`에 bash 리스트 문자열을 넣음 |
| 13+FPR GUI 전수 | 미완 | 전용 러너·표 없음 |
| Wave 1 전환 | 보류 | `legacy_migration_approved=false` 유지 |

## 2. 전달 인자 (측정)

### 2.1 엔진·모델 설정

출처: `.tmp/acf-product/config.yaml`, `iris-engine-selection.json`, `local_endpoint_probes.json`

| 키 | 값 |
|---|---|
| `model.provider` | `custom` |
| `model.default` | `gpt-oss:20b` |
| `model.base_url` | `http://127.0.0.1:11434/v1` |
| `model.ollama_num_ctx` | `65536` |
| 프로브 `ollama_num_ctx` (clean/ref) | `131072` (서버 보고) |
| 런타임 clamp | 로그 `Compressor window clamped ... 131072 -> 65536` |
| 엔진 슬롯 | `iris-agent.slot-0b0c55760140435c` |
| shell 승인 | `mode_id=run_everything` |
| setup | `core_ready: true` |

### 2.2 사용자 프롬프트 (채팅에 넣은 문장)

| 라운드 | conversation | 사용자 메시지 |
|---|---|---|
| clean/ref 텍스트 | sidecar 턴 | `Reply with just this exact text: IRIS-ACF-HELLO` |
| GUI 64k 마커 | cid 4 (01:44) | `Use the terminal tool exactly once to run this command: echo IRIS_ACF_NATIVE_TOOL_571. Then report the exact command output.` |
| retest shell | cid 2 (02:06) | `You MUST call the terminal tool. Do not invent output. Run exactly: echo IRIS_ACF_6B64D8077830 Then quote the tool result verbatim. ...` |
| retest browser | cid 3 (02:07) | `You MUST call browser_open exactly once with url https://example.com . Do not skip the tool. After the tool returns, reply with only OK.` (+ 자료 본문에 SSL 실패 메모 첨부) |

### 2.3 모델이 보낸 도구 인자 (Host가 받은 형태)

| 시각 | 도구 | request_id / tool_call_id | args_keys | 실제 실행 argv / 결과 |
|---|---|---|---|---|
| 02:06:40 | `terminal` → `shell.run` | `1e506ffe…` / `call_jtafzgdo` | `["cmd"]` | `cmd /c "['bash', '-lc', 'echo IRIS_ACF_6B64D8077830']"` → **exit 1** |
| 02:07:49 | `browser_open` | `58468b95…` / `call_gvt65ave` | `["url"]` | 별칭 후 navigate/open 성공, **ok:true** |

실패한 shell run 메타 (`.tmp/acf-gui-64k-retest/profile/.iris-light/runs/bea4d562dfc54659bc6aa45ef0214f00/meta.json`):

```json
{
  "run_id": "bea4d562dfc54659bc6aa45ef0214f00",
  "status": "failed",
  "exit_code": 1,
  "cwd": "...\\.tmp\\acf-gui-64k-retest\\profile",
  "interpreter": "cmd",
  "argv": ["cmd", "/c", "['bash', '-lc', 'echo IRIS_ACF_6B64D8077830']"],
  "owner": "shell.run"
}
```

stderr (CP949 깨짐 포함, 요지): `['bash'` 를 외부 명령으로 찾지 못함.

같은 프로파일에서 **Control 직호출**은 성공했다.

| run_id | argv | exit | stdout |
|---|---|---|---|
| `872df1a3…` | `cmd /c echo IRIS_ACF_6B64D8077830` | 0 | `IRIS_ACF_6B64D8077830` |
| `0e57cfe2…` | `cmd /c echo IRIS_ACF_3721D3E5D079` | 0 | `IRIS_ACF_3721D3E5D079` |

즉 Host `shell.run` 경로는 살아 있고, **모델이 넣은 `cmd` 값 형태**가 실패 원인이다.

### 2.4 스키마 별칭 전후 (이전 실패 → 재시험)

| 시점 | 증상 | 로그 |
|---|---|---|
| 11-25 23:12 / 11-26 01:50 | `browser.open` `unexpected argument: url` | `Tool browser_open returned error ... "error": "unexpected argument: url"` |
| 별칭 적용 후 02:08 | 동일 `url` 키로 **ok:true** | `tool browser_open completed (36.59s, 1511 chars)` |
| 초기 shell 스키마 이슈 | `cmd` → `missing command` (보고서 기록) | Speak `normalize_speak_invoke`: `cmd/shell→command`, `open+url→navigate` |

## 3. 라운드별 결과

### 3.1 Reference / Owned 텍스트 턴

| 항목 | Reference (`.tmp/acf-ref-turn`) | Owned clean (`.tmp/acf-clean`) |
|---|---|---|
| model | `gpt-oss:20b` | `gpt-oss:20b` |
| python | `~/.iris-light/agent/hermes-agent/venv/...` | `.tmp/acf-clean/iris-agent/venv/...` |
| sidecar_pid | 40512 | 3800 |
| startup_sec | 1.387 | 0.142 |
| turn_sec | 17.375 | 7.465 |
| terminal | `TurnFinished(text='IRIS-ACF-HELLO')` | 동일 |
| API (clean 로그) | in=2050 out=42 latency=1.9s | |

### 3.2 GUI context (ctx 부족)

`.tmp/acf-gui-context/gui-evidence.json`

| 항목 | 값 |
|---|---|
| model | `gpt-oss:20b` |
| tool_host_route | false |
| assistant_reported_marker | false |
| elapsed_sec | 6.711 |
| assistant 요지 | Ollama runtime context 16384 < Hermes 최소 64000. `ollama_num_ctx: 65536` 권고 |

sidecar: `Turn ended: reason=ollama_runtime_context_too_small ... runtime_context=16384`.

### 3.3 GUI 64k (마커·라우팅)

`.tmp/acf-gui-64k/gui-evidence.json`

| 항목 | 값 |
|---|---|
| gui_pid | 44024 (증거 스냅샷) / 로그상 후속 PID 다수 |
| conversation_id | 4 |
| elapsed_sec | 19.459 |
| tool_host_route | true |
| assistant_reported_marker | true |
| process.* | start/status/output/marker 모두 true |
| email_draft_ok | false (`compose dialog not opened`) |
| picker_open_and_alive | true |
| messages | user echo 요청 → assistant가 `IRIS_ACF_NATIVE_TOOL_571` plaintext 보고 |

같은 DB cid 2(11-25 23:10)는 shell+browser 후 assistant가 **한국 뉴스 요약**으로 빗나감 (도구 실패·후속 답변 이탈).

### 3.4 GUI 64k 강제 재시험 (스키마 별칭 후)

`.tmp/acf-gui-64k-retest/gui-evidence.json` · `native-tool-results.jsonl`

| 항목 | 값 |
|---|---|
| marker | `IRIS_ACF_6B64D8077830` |
| gui_pid | 436 |
| engine_slot | `iris-agent.slot-0b0c55760140435c` |
| elapsed_sec | 135.305 |
| shell_turn.tool_results | `shell.run` ok=false, error=`exit 1 · fail`, args_keys=`cmd` |
| shell_turn.assistant_has_marker | false |
| shell assistant 본문 | example.com 후속 질문으로 이탈 (마커 미인용) |
| browser_turn | `browser.open` ok=true, args_keys=`url` |
| control_shell_ok / control_marker | true |
| control_navigate_ok / control_open_url_ok | true |

API·착지 (retest `agent.log` + `turn_end_watch.log`):

| 세션 | API | 도구 | Turn ended | UDP done | land_db |
|---|---|---|---|---|---|
| `20261126_020617_6ec7d2` shell | #1 22.6s in=2050 out=48 · #2 18.7s | terminal 5.17s (1214 chars 결과) | api_calls=2 tool_turns=1 | emit done ok | cid=2 chars=207 |
| `20261126_020709_faa42f` browser | #1 39.2s in=2050 out=98 · #2 1.3s | browser_open 36.59s | api_calls=2 tool_turns=1 | emit done ok | cid=3 chars=100 |

## 4. 로그 발췌

### 4.1 모델 바인딩·라우팅

```text
TOOL_BIND name=terminal owner=iris action=shell.run fingerprint=43d1d206...
TOOL_BIND name=browser_open owner=iris action=browser.open fingerprint=5fcf1369...
TOOL_ROUTE model_tool_name=terminal action=shell.run owner=iris
TOOL_CALL request_id=1e506ffe... tool_call_id=call_jtafzgdo model_tool_name=terminal
TOOL_ROUTE model_tool_name=browser_open action=browser.open owner=iris
TOOL_CALL request_id=58468b95... tool_call_id=call_gvt65ave model_tool_name=browser_open
```

### 4.2 스키마 실패 (별칭 전)

```text
Tool browser_open returned error ... "error": "unexpected argument: url"
```

### 4.3 ctx 부족 (64k 설정 전)

```text
Ollama runtime context too small for Hermes tool use: model=gpt-oss:20b
runtime_context=16384 minimum_context=64000 estimated_request_tokens=15519 tool_count=115
Turn ended: reason=ollama_runtime_context_too_small
```

### 4.4 착지

```text
handler Turn ended ... model=gpt-oss:20b ...
emit done udp ok ...
worker finished_ok ...
ui land_db_ok turn=... cid=...
```

### 4.5 GUI stderr (부수)

`gui.log`에 Qt WebEngine GLES3→GLES2 fallback / shared context fatal 메시지가 반복된다. 이번 shell/browser 판정의 직접 원인은 아니다.

## 5. 구조

```text
사용자 채팅 (gpt-oss:20b / Ollama :11434 / num_ctx 65536)
  → Iris GUI Worker / Sidecar
       → TOOL_CALL (tool_call_id, args)
            → Host TOOL_ROUTE (owner=iris)
                 → normalize_speak_invoke (cmd→command, open+url→navigate)
                 → shell.run / browser.open
                      → runs/<id>/meta.json + stdout/stderr
                 → tool result → 모델 2차 API
            → Turn ended → UDP done → land_db_ok
```

갈라진 지점:

1. **ctx 16384**면 도구 루프 진입 전 종료 (`ollama_runtime_context_too_small`).
2. **별칭 전** `url`/`cmd` 키는 스키마에서 거절.
3. **별칭 후 shell**은 스키마는 통과하나, 모델 `cmd`가 bash 리스트 문자열이면 Windows `cmd /c`에서 exit 1.
4. Control 직호출은 평문 `echo MARKER`라 성공. 모델 경로와 결과가 갈라진다.

## 6. 코드 리뷰 (한 일 / 막지 못한 일)

| 지점 | 한 일 | 막지 못한 일 |
|---|---|---|
| Speak normalize | `cmd`/`url` 별칭 | 모델이 `cmd`에 `['bash', …]` 문자열을 넣는 실행 의미 오류 |
| Host routing | `owner=iris` 라우팅·착지 | 도구 실패 후 assistant가 마커를 인용하지 않고 이탈 |
| Control path | shell/navigate/open 성공 증거 | 모델 경로와 동일 argv를 강제하지 않음 |
| 설정 | `ollama_num_ctx: 65536` | 프로파일/시점에 따라 16384로 뜨던 런 |
| 이메일·피커 | 피커 alive | compose dialog not opened |

하지 않은 일: 13+FPR 전수, Reference 동등 GUI 표, `legacy_migration_approved` 승격, 기존 홈 전환 롤백.

## 7. 같은 세션의 `gemma4:12b` (참고)

`gpt-oss:12b`는 없다. 요청의 12b에 가장 가까운 동일 로그 스트림 기록:

| 시각 | 모델 | 메모 |
|---|---|---|
| 2026-11-25 23:03:19 | `gemma4:12b` | 동일 echo 프롬프트. sanitizer가 `terminal.run_command` → `terminal_run_command` 로 수리. 이후 text_response로 종료 |

본 문서의 본선 판정 대상은 아니다.

## 8. 개선안

| 빈 자리 | 다음 |
|---|---|
| 모델 shell argv | `cmd` 값이 리스트/bash 래핑이면 Windows에서 평문 `echo`/`cmd /c`로 coerce하거나, 실패를 모델에 명확히 돌려 재시도 유도 |
| 마커 검증 | 도구 실패·성공과 무관하게 assistant가 마커를 인용했는지 계약 assert |
| 13+FPR | 격리 profile + Reference 동일 조건 표 |
| 전환 | shell 성공 왕복 후에만 `legacy_migration_approved` 재판정 |

## 9. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| OpenAI tool arg aliases | schema aliases | Speak 경계 coerce로 충분했던 구간은 이미 닫힘 |
| 찾지 못함 | gpt-oss 전용 Windows shell argv normalizer 패키지 | 로컬 coerce·계약 테스트로 충분 |

## 10. 증거 경로

| 파일 | 역할 |
|---|---|
| `.tmp/acf-gui-64k-retest/gui-evidence.json` | 강제 재시험 종합 |
| `.tmp/acf-gui-64k-retest/native-tool-results.jsonl` | shell fail / browser ok |
| `.tmp/acf-gui-64k-retest/profile/.iris-light/runs/*/meta.json` | 실 argv·exit |
| `.tmp/acf-gui-64k/gui-evidence.json` | 64k 마커·라우팅 |
| `.tmp/acf-gui-context/gui-evidence.json` | ctx 16384 실패 |
| `.tmp/acf-clean/turn-evidence.json` | Owned HELLO |
| `.tmp/acf-ref-turn/turn-evidence.json` | Reference HELLO |
| `.tmp/acf-product/config.yaml` | 모델·num_ctx 인자 |
| `.tmp/acf-product/logs/agent.log` | API·TOOL_*·Turn ended |
| `.tmp/acf-gui-64k-retest/profile/.iris-light/logs/turn_end_watch.log` | UDP done / land_db |
| `docs/code-review/final-gate-closure-report-2026-11-26.md` | Gate 판정 본문 |

## 11. 조치

1. 모델 ID 표기는 증거 기준 **`gpt-oss:20b`** 로 통일한다.
2. P0는 모델 `shell.run` argv coerce 또는 동등 성공 왕복 증거.
3. 그다음 13+FPR · Reference 동등 · 전환 가드.
4. 커밋·push는 사용자 요청 시에만.

## 12. 확인한 사실 (요약 표)

| 사실 | 출처 | 라벨 |
|---|---|---|
| 기본 모델 `gpt-oss:20b`, base_url `:11434/v1`, num_ctx 65536 | config.yaml | measured |
| HELLO 텍스트 턴 Owned/Reference PASS | turn-evidence.json | measured |
| browser `url` 별칭 후 ok:true | gui-evidence retest + agent.log | measured |
| shell 모델 경로 exit 1, argv가 bash 리스트 문자열 | runs/bea4d562…/meta.json | measured |
| Control shell 동일 마커 echo exit 0 | runs/872df1a3… | measured |
| 착지 UDP done + land_db_ok | turn_end_watch.log | measured |
| `gpt-oss:12b` 실행 기록 없음 | `.tmp` 전수 검색 | measured |
| `gemma4:12b` 한 턴 존재 | agent.log 23:03 | measured |
