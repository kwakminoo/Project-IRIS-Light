# Prompt: Iris Agent Phase 5 — in-process 합침 (검증 먼저 → 조건부 병합)

기준 문서:
- `docs/code-review/Iris-Agent-Phase5-in-process-검증계획.md` (용어·단점 보완·착수 조건)
- `docs/prompts/Iris-Agent-Phase5-prove-채팅시퀀스.md` (채팅 A~E 본문)
- `docs/code-review/completed/Iris-Agent-Hermes기반-구현경로.md` §4 5단계, §10.1(이미 CLOSED)

전제: 1~4단계 + §10.1 게이트 1~4는 **완료**. Phase 5는 선택이나, 제품·도메인상 **합침이 목표**.  
초파리 뇌·git commit은 범위 밖(요청 있을 때만).

```text
Context:
- 지금: Iris(Qt)와 에이전트 루프가 별 프로세스. 말 턴은 주로 HTTP :8642 (Hermes gateway).
  소유권(툴 native seed·설정·채팅 정본·supervisor)은 이미 Iris Agent.
- 목표: 같은 OS 프로세스 안에서 에이전트 루프를 돌린다. 폴더/패키지는 나누고,
  UI 스레드와 에이전트 워커 스레드는 나눈다. Ollama는 계속 별 프로세스 허용.
- 합침 이유: 제품·도메인 = Iris Agent 한몸. “엔진만 죽는 반쪽 제품”을 허용하지 않음
  (죽음 = 고칠 결함). 예전 프로세스 kill로 하던 복구는 워커/루프 리셋으로 대체.
- pin: vendor/iris-agent-runtime/PIN. 최신 main 자동 추격 금지. 검증 후 PIN을
  의도적으로 올린다. in-process import도 동일 pin 기준선.
- 금지: Prove 통과 전 :8642 제품 경로 삭제·전면 병합. 클릭/사이드바→에이전트 턴.
  새 hermes_* 모듈 남발. Qt 메인 스레드에서 루프 블로킹. agent→ui 위젯 import.

Goal (순서 고정. 채팅 하나 = 단계 하나. 새 채팅에서만 실행):

Prove 0 — 워커에서 루프(또는 그 자리 스탠드인) 기동. QWidget 비터치. pin/홈 사용.
  자검: _check_iris_agent_phase5_prove0. 병목·:8642 사용 여부 보고.
Prove 1 — 스레드 경계: 워커→UI는 pyqtSignal만. 슬롯로 예외 안 샘. UI 블로킹 없음.
  자검: _check_iris_agent_phase5_prove1 (+ prove0).
Prove 2 — no-console. 에이전트 예외는 failed/오류로 봉쇄. 프로세스 kill로 “해결” 금지.
  자검: _check_iris_agent_phase5_prove2 (+ prior) + no-console 회귀.
Prove 3 — 핫리스타트 대체: UI 유지 + 워커/루프 리셋 API. pin == PIN 자검.
  gateway hang·config reload·soft-hang 중 무엇을 리셋으로 커버하는지 표로.
  자검: _check_iris_agent_phase5_prove3 (+ prior). “Merge 허용?” PASS/FAIL 한 줄.

Merge (Prove 0~3 전부 PASS + 사용자가 Merge 채팅을 명시할 때만):
  - 제품 speak 기본 경로 = in-process 루프 (워커 스레드).
  - :8642는 fallback/dev만 또는 제품 기본에서 제거.
  - ensure_iris_agent_runtime / reset_agent_loop 와 정합.
  - 패키지: iris/ui(얼굴) ↔ iris/agent 또는 infrastructure(루프). ui→agent만.
  - 보고서 Phase5-merge + 검증계획 착수 조건 체크 완료.
  - 회귀 시 in-process 기본을 되돌리고 별 프로세스 유지.

Constraints:
- /poteto-mode Feature. 한국어 진행 요약.
- qt-slot-abort, no-console-windows, iris-exe thin launcher.
- 커밋은 사용자 요청 있을 때만.
- Prove FAIL → 병합 금지. 같은 Prove만 새 채팅에서 재시도.
- 5단계 실패를 1~4 일체화 실패로 말하지 않음. 반대로 Prove 전 병합 성공 주장 금지.

Interface / 손댈 후보 (Prove부터 최소):
- iris/ui/workers/hermes_workers.py (QThread·signal 패턴 재사용)
- iris/infrastructure/agent_runtime.py (ensure·reset)
- iris/infrastructure/agent_tool_registry.py (워커에서 native, Qt 금지)
- (Merge 시) hermes_client / gateway 호출을 speak 기본에서 강등
- 자검: iris/system/_check_iris_agent_phase5_prove{0,1,2,3}.py
- 문서: docs/code-review/Iris-Agent-Phase5-prove{N}.md , 검증계획 체크리스트

검증 (단계별):
0) prove0 + phase1 + phase4b + phase2_5
1) prove1 + prove0
2) prove2 + prove0–1 + tests.test_no_console_window (해당 시)
3) prove3 + prove0–2 ; Merge 허용 여부 명시
Merge) prove0–3 + phase1/2_5/3/4/4b + settings + hermes_required

Work order:
- 이 프롬프트만으로 한 채팅에서 0→Merge 전부 하지 말 것.
- 시퀀스 문서의 채팅 A→B→C→D→E 본문을 새 창에 하나씩 붙인다.
- 첫 실행 = 채팅 A (Prove 0)만.
```

## 새 채팅에 붙일 시작 한 줄

```text
@docs/prompts/Iris-Agent-Phase5-in-process-구현프롬프트.md @docs/code-review/Iris-Agent-Phase5-in-process-검증계획.md @docs/prompts/Iris-Agent-Phase5-prove-채팅시퀀스.md /poteto-mode
```

이어서 시퀀스 문서의 **채팅 A** 본문만 붙인다. Prove 1 이후는 각각 새 채팅 + 해당 본문.
