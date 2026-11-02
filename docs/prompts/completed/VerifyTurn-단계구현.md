# VerifyTurn 단계 구현 프롬프트

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-PROMPT-2026-1028-VERIFYTURN |
| 작성일 | 2026-10-28 |
| 기준 | PEV 조사 합의 (Hermes E 유지 + CRITIC식 코드 V) |
| 선행 | `docs/prompts/파일생성-검증층-1to3-구현프롬프트.md` |
| 실행 | 단계마다 **새 에이전트 채팅**. 자검 통과 후에만 다음 단계 |
| 금지 | Hermes 교체, LLM-only verifier, goal LLM 분류기 전면 교체, 펜스 전면 폴백, 커밋은 사용자 요청 전 금지 |

## 운용 규칙

1. 한 단계 = 한 프롬프트 = 한 구현 채팅.
2. 단계 끝에서 반드시 아래 **게이트 명령**을 돌린다. 실패면 같은 단계에서 수정·재검증.
3. 통과 증거(명령 출력 요약)를 남긴 뒤 다음 단계 프롬프트를 새 채팅에 넣는다.
4. 데이터 모양은 단계 0에서 고정한다. 이후 단계는 표에 행·필드만 추가한다.

## 단계 0. 데이터 모양 (구현 전 고정, 코드는 1에서)

```text
TurnEvidence:
  tool_ok_count: int
  tool_written: bool
  verified_path: str
  content_match: bool | None   # 2단계에서 채움
  empty_reply: bool
  assistant: str
  goal: str

VerifyAction: display | ask | local_write | failover | stop
VerifyResult:
  display: str
  actions: list[VerifyAction...]
  suppress_voice_followup: bool

정책 표 (파일 행만 1~3):
  kind=file_create
  claim? + !evidence → append CHAT_ONLY
  fences+ unambiguous name + !tool_written → local_write
  empty_reply|CHAT_ONLY path + file goal + tool_ok==0 → failover or explicit fail
```

---

## 단계 1. VerifyTurn 골격 + 허위완료·assistant 파일명

```text
/poteto-mode Feature

Goal: Iris 채팅 턴 종료 시 VerifyTurn 한 진입점으로 파일 허위완료·로컬쓰기를 모은다.
User goal: 말로만 「작성했다」면 실패 표시. 코드+이름 분명하면 Iris가 파일을 쓴다.

Data shape: TurnEvidence, VerifyResult (위 단계 0). Organizing structure: iris/runtime/turn_verify.py 모듈 + 파일 정책 함수 표.

Do:
1. Create iris/runtime/turn_verify.py
   - verify_file_create_turn(evidence, *, plan_local_write_fn optional) -> VerifyResult
   - 내부에서 settle_completion_claim / plan_local_file_writes 를 호출하거나 동일 규칙을 이관.
2. file_write_claim._CLAIM_RE 보강: 작성을 완료|코드를 짰|코드는 작성|작성을 마쳤
   turn_followthrough._DONE 과 표시 게이트가 같은 완곡 표현을 놓치지 않게 정합.
3. plan_local_file_writes: goal names 비고 fences==1 이면 named_rel_paths(assistant) 가 정확히 1개일 때 write.
4. MainWindow._on_chat_finished / _gate_chat_completion / _maybe_local_file_create_write
   를 VerifyTurn 호출로 묶는다. 동작 동일·진입점만 통일. 위키 게이트 건드리지 말 것.
5. 자검 확장 iris/ui/_check_file_write_claim.py + (선택) iris/runtime/_check_turn_verify.py

Gate:
.venv\Scripts\python.exe -m iris.ui._check_file_write_claim
.venv\Scripts\python.exe -m iris.runtime.turn_followthrough
새 _check_turn_verify 가 있으면 그것도.

Out: 테트리스 문장 CHAT_ONLY. goal 무명+assistant tetris_king.py+펜스1 → write plan.
Commit: no unless user asks.
```

**통과 기준.** 게이트 명령 exit 0. `_on_chat_finished`가 VerifyTurn을 탄다 (grep/자검).

---

## 단계 2. 쓰기 성공 = 내용 readback (content_match)

```text
/poteto-mode Feature

Depends on: 단계 1 통과.
Goal: project.write_file / write_project_file 성공 판정에 UTF-8 readback 일치를 넣는다.
false "썼다" (ok인데 내용 다름)를 막는다.

Do:
1. write_project_file (및 stream 최종) 직후 path.read_text 와 요청 content 비교.
   불일치 → ok false + error. content_match 필드를 결과에 실을 수 있으면 실음.
2. verified_write_path / turn_write_evidence / VerifyTurn 이 content_match=false 면 증거 없음으로 취급.
3. IDE visible 과 write ok 를 OR 하지 말 것 (기존 계약 유지).
4. 자검: temp 파일 write 후 내용 바꾸면 증거 실패. 정상 write면 통과.

Gate:
.venv\Scripts\python.exe -m iris.ui._check_file_write_claim
관련 project_ops / control 자검이 있으면 함께
.venv\Scripts\python.exe -c "from iris.system.project_ops import ..." 최소 스모크 가능하면.

Commit: no unless user asks.
```

**통과 기준.** readback 불일치 시 ok false. VerifyTurn이 그 경로를 실패로 표시.

---

## 단계 3. 빈 응답·도구 0 → failover / 명시 실패

```text
/poteto-mode Feature

Depends on: 단계 1·2 통과.
Goal: 파일 생성 goal 인데 도구 0 + (빈 응답 또는 허위완료 CHAT_ONLY)면
followthrough 말만 반복하지 말고 failover 또는 명시 실패 문구.

Do:
1. VerifyTurn 파일 정책에 empty_reply / claim+no evidence 분기.
2. failover_prefs 가 켜져 있고 체인이 있으면 기존 HermesChatWorker attempts / failover 경로 재사용 한 턴.
3. 없으면 활동·채팅에 「도구로 파일을 만들지 못했다…」 명시. 성공처럼 두지 말 것.
4. 빈 응답 턴은 FILE_FOLLOWTHROUGH_UTTERANCE continue 보다 failover/명시실패 우선
   (turn_followthrough decide 조정 또는 VerifyTurn이 suppress continue).
5. 자검: mock evidence 로 분기 검증.

Gate:
.venv\Scripts\python.exe -m iris.ui._check_file_write_claim
.venv\Scripts\python.exe -m iris.runtime.turn_followthrough
failover 관련 자검 있으면 함께.

Commit: no unless user asks.
```

**통과 기준.** 빈+도구0+파일goal → failover 시도 또는 명시 실패. 무한 「호출하라」만으로 끝내지 않음.

---

## 단계 4 (선택, 1~3 후). 위키·실행 행을 같은 표로

범위가 커지므로 1~3 안정화 후 별 프롬프트. 이번 연속 실행의 기본 종료점은 **단계 3**.

---

## 부모 채팅 체크리스트

- [x] 단계 1 프롬프트 → 새 채팅 구현 → 게이트 통과
- [x] 단계 2 동일
- [x] 단계 3 동일
- [x] 사용자에게 단계별 증거 보고
