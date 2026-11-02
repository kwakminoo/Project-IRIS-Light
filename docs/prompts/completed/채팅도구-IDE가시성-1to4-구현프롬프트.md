# 채팅 도구 강제 · IDE 가시성 1to4 구현 프롬프트

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-PROMPT-2026-1028-TOOL-IDE-VIS |
| 작성일 | 2026-10-28 |
| 기준 | 세션 조사 합의 (제목 404 / 도구 미호출 / openFile 3.5s / 터미널 비가시) |
| 선행 | 대화 조사. 코드 리뷰 보고서는 선택 |
| 실행 | 단계마다 **새 에이전트 채팅**. 게이트 통과 후에만 다음 단계 |
| 금지 | Hermes 통째 교체, LangGraph 도입, openFile 타임아웃 **삭제**(무한), bridge_fallback 재도입, ConPTY/Electron 호스트 교체(별 스파이크), 커밋은 사용자 요청 전 금지 |

## 운용 규칙

1. 한 단계 = 아래 해당 단계 코드 블록만 새 채팅에 붙여 넣는다.
2. 단계 끝에서 **Gate** 명령을 돌린다. 실패면 같은 단계에서 수정·재검증.
3. 통과 증거(명령 출력 요약 + 필요 시 수동 확인 한 줄)를 남긴 뒤 다음 단계 프롬프트를 새 채팅에 넣는다.
4. 데이터 모양은 단계 0에서 고정한다. 이후 단계는 표에 필드만 추가한다.
5. 모델 품질(어떤 LLM이 도구를 잘 고르는지)은 이 프로그램 밖이다. 스킵한다.

## 배경 (한 단락)

채팅 제목은 본문과 다른 Hermes HTTP 경로라 Nemotron 등에서 404가 반복된다. 에이전트가 도구를 안 부르면 `도구 호출 없음`만 찍히고 IDE에는 아무 일도 없다. `project.write_file`은 `createFile`(디스크) 후 `openFile`(탭, 구 3.5s)이라 탭 실패가 전체 write를 err로 만들 수 있다. `project.run`은 Theia 통합 터미널 **재사용**이며 새 탭을 보장하지 않는다. ConPTY 근본 수정은 이 1to4에 넣지 않는다.

## 단계 0. 데이터 모양 (구현 전 고정)

```text
TitleRoute (기존 SummaryRoute / BackendRoute 재사용):
  backend, model, base_url, api_key, target(HermesInferenceTarget|None)
  제목 요청 전: 본문과 동일하게 resolve_hermes_inference + (가능하면) set_inference_model(target=)
  실패: 활동줄만. 본문·도구 차단 금지.

ToolForcePolicy:
  first_llm_step: tool_choice = required (지원 프로바이더만)
  exit_tool: respond | chat_only  (이름 하나로 고정. Hermes respond 우선)
  after_real_tools: tool_choice = auto  (무한 루프 금지)
  user_turn: 툴 호출 개수 >= 1 허용 (정확히 1 금지. 병렬·연속 OK)
  honesty: 사이드이펙트 주장인데 exit_tool만이면 거절/재시도 (얇은 게이트)

OpenFileBudget:
  enqueueFrontend openFile timeout_ms = 15000
  createFile: 디스크 동기. 프론트 타임아웃 없음
  write_file result:
    on_disk / content_match / opened / visible 분리
    open 실패 ≠ 디스크 실패 (탭 soft-fail 또는 err 메시지에 on_disk 명시)

RunVisibility:
  project.run / write ok → 채팅 ToolShellBlock(또는 동등 카드)에 command·요약
  터미널: ensureTerminal 재사용 유지. 패널 reveal 강화. createTerminal 매번 강제 금지
```

---

## 단계 1. 채팅 제목 ↔ 본문 inference 동기화

```text
/poteto-mode Feature

Goal: 채팅 목록 제목 요청이 본문 Hermes 채팅과 같은 inference target(model+provider base_url/api_key)을 쓰게 한다.
User goal: Nemotron 등으로 본문은 되는데 `채팅 제목 실패: Hermes: HTTP 404: model '…'`가 매 턴 반복되지 않게 한다.

Depends on: 없음 (1to4의 첫 단계).

Data shape: TitleRoute / HermesInferenceTarget (단계 0). Organizing structure: _request_chat_title + ChatTitleWorker/collect_reply 경로에 sync 한 곳.

Do:
1. 읽기: iris/ui/window/main_window.py `_request_chat_title`, `_summary_route_for`
   iris/ui/workers/chat_title_worker.py, iris/ui/workers/backend_call.py `_hermes`
   iris/ui/workers/hermes_workers.py 의 set_inference_model(target=…) 본문 경로
   iris/infrastructure/hermes_client.py resolve_hermes_inference
2. 제목 워커 시작 전(또는 _hermes 진입 시) 본문과 같이 target을 싣는다.
   - SummaryRoute/BackendRoute에 target이 있으면 set_inference_model(model, target=target) 후 stream_chat
   - 또는 HermesClient.stream_chat이 custom endpoint를 받도록 본문과 동일 인자 전달
3. 404 등 제목 실패는 기존처럼 활동줄만. 본문 턴·도구·DB 메시지에 쓰지 말 것.
4. TITLE_BASIS_LAST 매 턴 재시도는 유지해도 된다. sync 후 404가 줄는지가 본 게이트.
5. 프로바이더가 sync를 거부하면(예외) 제목만 스킵·휴리스틱 가능. 본문을 깨지 말 것.
6. 자검: 기존 chat_title_worker self-check 유지. 가능하면 sync 호출을 mock하는 최소 자검 추가
   (실제 NVIDIA 키가 없어도 「target이 stream 경로에 전달됨」을 assert).

Gate:
.venv\Scripts\python.exe -m iris.ui.workers.chat_title_worker
관련 자검이 있으면 함께. 수동: Iris 재시작 → Nemotron(또는 제목 404 나던 모델)로 한 턴 → 활동줄에 `채팅 제목 실패: Hermes: HTTP 404`가 더 이상 안 뜨거나, 뜨더라도 원인 로그가 sync 전후와 다름을 기록.

Out: 제목 경로가 본문과 같은 target을 쓴다.
Commit: no unless user asks.
Do not: openFile 예산, tool_choice, 셸 카드, ConPTY.
```

**통과 기준.** 게이트 exit 0. 수동 한 턴에서 제목 404가 사라지거나 sync 누락이 코드상 불가능해짐(자검).

---

## 단계 2. 도구 채널 의무 (≥1) + respond/chat_only

```text
/poteto-mode Feature

Goal: 사용자 턴에서 모델이 툴 없이 말만 하고 끝나는 경로를 막는다. 매 턴 툴 ≥1. 순수 답변은 respond(또는 chat_only) 탈출 툴.
User goal: 「실행해줘」에 도구 호출 없음 + 텍스트만 「실행했다」가 반복되지 않게 한다.

Depends on: 단계 1 통과.

Data shape: ToolForcePolicy (단계 0). Organizing structure: Hermes agent 설정/엔진 경로에 required+respond. Iris는 인식·unwrap·얇은 정직 검사만.

Do:
1. 조사(구현 채팅 초반에 짧게):
   - 설치된 Hermes/Iris Agent에 agent.tool_choice / respond 툴이 있는지
     (NousResearch hermes-agent PR #145164 패턴: required + respond(message) + intake unwrap)
   - 없으면 Iris 벤더 핀·패치 또는 engine 경로에서 chat_completions에만 required+respond를 넣는 최소 경로
2. 계약:
   - 사용자 메시지 직후 첫 LLM 스텝: tool_choice=required (지원 경로만)
   - 실툴 실행 후 재호출: tool_choice=auto (무한 루프 금지)
   - respond/chat_only만 오면 일반 assistant 텍스트로 unwrap. 활동줄에 도구 진행이 남게(또는 「respond ok」)
   - 한 응답에 실툴 여러 개(병렬) 허용. 「정확히 1개」 강제 금지
3. 얇은 정직 검사 (키워드 나열 확장 금지. 한 갈래만):
   - 사용자 goal이 파일 생성/실행/설치 등 사이드이펙트이고, 이번 턴 실툴 ok가 0이며 exit_tool만이면
     성공으로 끝내지 말고 재시도 1회 또는 명시 실패
   - 기존 VerifyTurn / CHAT_ONLY / file_create 경로와 충돌 없이 합류
4. 프로바이더 400 (과거 docs: Gemini·Hermes에 tool_choice 넣으면 400):
   - 지원 안 하면 그 백엔드만 auto 유지 + 활동줄에 한 줄. 전체 채팅을 죽이지 말 것
5. 자검:
   - required가 켜진 설정/플래그 assert
   - respond unwrap → plain text
   - 「실행」goal + tool_ok==0 + respond only → 성공 표시 아님
6. LangGraph·별도 Iris 앞단 툴라우터 프로세스 신설 금지.

Gate:
Hermes/엔진 관련 자검 (있는 것 + 이번 단계에 추가한 _check_*)
.venv\Scripts\python.exe -m iris.runtime._check_turn_verify
.venv\Scripts\python.exe -m iris.ui._check_file_write_claim
수동: Iris Agent 켠 채 「지금 열린 프로젝트가 뭔지 알려줘」(respond/상태 툴 가능)와
「print_calendar.py 실행해줘」(project.run 기대) 각 1회.
후자는 tool.started 또는 동등 진행이 있어야 하고, 전자는 빈손 종료가 아니어야 한다.

Out: 도구 호출 없음만으로 사이드이펙트 성공 연출이 구조적으로 어려워진다.
Commit: no unless user asks.
Do not: openFile 15s, 셸 카드 UI, ConPTY.
```

**통과 기준.** 게이트 exit 0. 수동 실행 요청에 도구 진행이 보인다. 잡담/상태 질문은 respond로 끝나도 된다.

---

## 단계 3. openFile 15s + create/open 분리

```text
/poteto-mode Feature

Goal: openFile 프론트 대기를 15초로 올리고, 디스크 성공과 탭 가시성을 결과 필드에서 분리한다.
User goal: 달력은 탭이 뜨고 테트리스는 openFile timeout으로 「안 만든 것처럼」 보이는 일을 줄인다.

Depends on: 단계 1·2 통과 (2와 독립 가능해 보이면 1만 선행해도 됨. 기본은 1→2→3).

Data shape: OpenFileBudget (단계 0).

Do:
1. integrations/iris-ide/bridge/standalone-bridge.js
   openFile/gotoFile enqueueFrontend timeout 3500 → 15000
   createTerminal 3500은 이번 단계에서 필수가 아님(건드리면 이유 주석). runTerminalCommand 15s는 유지 가능
2. bridge_fallback / opened:true 위장 재도입 금지 (정직 계약 유지)
3. iris/ui/control_actions/project.py project_write_file (iris_ide 경로):
   - create_file 성공 후 open_file 실패 시
     디스크 경로는 payload에 on_disk=true / path / rel_path
     opened/visible=false
     전체 write를 「파일 없음」과 동일하게 취급하지 말 것
   - 정책 선택(구현 채팅에서 하나로 고정하고 자검에 적기):
     A) open 실패 = err 이지만 CHAT_ONLY·Verify는 on_disk면 wrote 인정 가능
     B) open 실패 = ok=true + opened=false 경고 (탭 soft-fail)
   권장: A에 가깝게. 탭은 실패로 남기되 「채팅에만」오진을 줄일 것
4. _bridge_call_pumping 기본 timeout(20s)과 15s open이 맞물리게. UI 스레드 블록으로 폴러 죽이는 경로 만들지 말 것 (기존 pumping 유지)
5. 자검: iris/system/_check_ide_link.py 등 timeout 문구·예산 assert 갱신
   open 실패 시 on_disk 필드 자검

Gate:
.venv\Scripts\python.exe -m iris.system._check_ide_link
관련 iris_ide bridge 자검
(번들 필요 시) iris_ide_runtime.sync_workspace_build — openFile 15s가 설치본 bridge에 들어갔는지 확인
수동: Companion에서 연속 write 2회(짧은 파일 + 긴 파일). 둘 다 디스크에 있고, 가능하면 탭도 연다.

Out: 3.5s 하드 컷 제거(상한 15s). create와 open의 실패 의미가 갈라진다.
Commit: no unless user asks.
Do not: 타임아웃 0/무한, ConPTY, 셸 카드.
```

**통과 기준.** 브리지 openFile 예산 15000. 자검 통과. 연속 쓰기에서 디스크 유실 없음.

---

## 단계 4. 실행·쓰기 가시성 (셸/툴 카드 + 터미널 드러내기)

```text
/poteto-mode Feature

Goal: project.run / 의미 있는 write 성공을 채팅에 Cursor식 카드로 남기고, IDE 터미널 패널이 접혀 있어도 사용자가 「돌았다」를 채팅에서 보게 한다.
User goal: pip·실행이 어느 터미널인지 모를 때 채팅 카드로 추적 가능.

Depends on: 단계 1·2·3 통과.

Data shape: RunVisibility (단계 0).

Do:
1. 기존 iris/ui/chat/chat_panel.py insert_tool_block / ToolShellBlock 재사용
2. project.run ok/err 요약을 카드로 삽입 (command, summary, exit, via=theia_terminal 등). stdout 전문 덤프 금지(길면 자름)
3. project.write_file ok 시 짧은 카드 또는 chip (rel_path, opened true/false)
4. 도구를 안 부른 턴에는 카드를 만들지 않는다. 그게 빈손 신호다 (단계 2가 본체)
5. 터미널: ensureTerminal 재사용 유지. run 시 터미널 패널 reveal/open(reuse) 강화만. 매회 createTerminal 강제 금지
6. ConPTY / Electron 호스트 교체 / newTerminal 항상 생성 = 이 단계 금지 (별 스파이크 문서만 TODO 한 줄 가능)
7. 자검: 카드 렌더·insert_tool_block 스모크. project.run 페이로드 → 카드 필드 매핑

Gate:
관련 chat / project_run 자검
.venv\Scripts\python.exe -m iris.ui._check_project_run_terminal  (또는 동등)
수동: 「달력 스크립트 실행해줘」→ 채팅에 셸 카드 + (가능하면) IDE 터미널에 출력.

Out: 실행·쓰기의 사용자 가시성. 근본 ConPTY는 미해결로 명시.
Commit: no unless user asks.
```

**통과 기준.** 수동 실행 턴에 채팅 카드가 보인다. 도구 0인 턴에는 가짜 카드가 없다.

---

## 프로그램 종료

- [ ] 단계 1~4 게이트 통과 증거가 각 채팅에 남음
- [ ] `docs/prompts/채팅도구-IDE가시성-1to4-구현프롬프트.md`만 completed로 옮김 (`git mv` → `docs/prompts/completed/`) — 코드까지 확인된 뒤
- [ ] ConPTY 스파이크는 이 문서 밖. 필요 시 별 프롬프트

## 차용 (구현 시 참고)

| 이름 | 가져올 부분 | 가져오지 않음 |
|---|---|---|
| Hermes agent tool_choice=required + respond | 와이어 required, respond 탈출, unwrap | Anthropic thinking 강제, LangGraph |
| OpenAI Agents SDK forcing_tool_use | 툴 후 auto 리셋으로 루프 방지 | SDK 통째 도입 |
| Iris ToolShellBlock | 채팅 카드 UI | Cursor Electron 터미널 호스트 |

## Appendix. 기각

| 아이디어 | 이유 |
|---|---|
| openFile 타임아웃 삭제 | 폴러 사망 시 무한 대기. 15s 상한 |
| Iris 앞단 별도 툴라우터 프로세스 | Hermes 루프와 중복 |
| 매 턴 툴 정확히 1개 | write+run 불가 |
| 재사용 = ConPTY 해결이라고 말하기 | UX 계약일 뿐. 근본은 별 트랙 |
