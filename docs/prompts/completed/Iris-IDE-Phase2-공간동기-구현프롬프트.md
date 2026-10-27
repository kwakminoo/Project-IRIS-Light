# Prompt: IRIS IDE Phase 2 — 공간 동기 (work_root = IDE 폴더)

> **상태 (2026-10-28): 구현·자검 완료.** 보관용. 다음 = 단계표 3단계(Companion 손맛) 프롬프트는 오케스트레이터가 작성.

기준 문서:

- `docs/code-review/Iris-IDE-커서조작-일체화-단계표.md` §5.2
- `docs/code-review/IDE-커서처럼-조작-현황.md` (worktree ↔ 열린 폴더)
- Phase1 완료: `docs/prompts/completed/Iris-IDE-Phase1-정직화-구현프롬프트.md`

3~5단계(드래그·진단·셸 브랜드)와 에이전트 뇌 Theia 흡수는 **금지**.

```text
Context:
- work_root_for(conversation_id) 가 대화별 git worktree(또는 본 체크아웃)를 고른다.
- project.write_file / project.run 등은 bound IDE session.workspace_root 와
  work_root 가 다르면 지금 err_result("… call ide.open_folder first") 로 끝난다.
  에이전트가 open_folder를 빼먹으면 쓰기·실행이 침묵에 가깝게 실패한다.
- 목표: 불일치면 쓰기/실행 전에 IDE 워크스페이스를 work_root 로 맞춘 뒤 진행.
  맞추기 실패만 명시 오류(원인·필요 폴더·hint).
- Phase1 정직화(visible/save/open 가짜 성공)를 깨지 말 것.

Goal (이 채팅에서 2단계만):

1) 계약
   - project.write_file / project.run (및 동일 불일치 가드가 있는 project.* )에서
     work_root != bound workspace 이면:
     a) ide.open_folder(path=work_root) 또는 동등한 기존 API로 폴더를 연다
        (new_window 기본·Companion 타일 계약 유지 — ide-new-window / tile-8020 규칙).
     b) 성공 후 session.workspace_root 가 work_root 와 같다고 확인한 뒤에만 쓰기/실행.
     c) 실패 시 err_result — project_root, bound_workspace_root, open_folder_path, error.
   - 침묵 거절 금지. “call ide.open_folder first”만 던지고 끝내기 금지(자동 맞춤이 기본).
   - 이미 일치하면 open_folder를 다시 치지 않음(멱등).

2) Qt/슬롯 안전
   - 메인 스레드 블로킹·frameless+QFileDialog·슬롯 예외(0xC0000409) 회귀 금지.
   - 기존 _call_on_ui / _bridge_call_pumping / ide.open_folder 경로를 재사용.
   - main_window 주석의 “동기 ide.open_folder 재진입” 함정을 피할 것.

3) 자검
   - 불일치 → 자동 open 시도 → 성공/실패를 assert 하는 체크 모듈
     (신규 iris/ui/_check_ide_workspace_sync.py 또는 기존 확장).
   - 일치 시 open_folder 호출 0회(목/카운터).
   - Phase1 자검 회귀: _check_ide_link, _check_iris_ide_bridge.

4) 스킬/넛지 (최소)
   - vibe/코딩 스킬·hermes_memory_nudge에 “폴더 불일치면 Iris가 맞춘다 / 실패면 오류”
     한 줄. 대규모 스킬 개편 금지.

Constraints:
- 3단계 드래그·콘솔, 4단계 LSP, 5단계 시작화면 브랜드 금지.
- Theia AI / 에이전트 루프 IDE 흡수 금지.
- 커밋은 사용자 요청 있을 때만.
- no-console / qt-slot-abort / companion tile / new-window 계약 유지.
- 인라인 import 금지(파일 상단). ponytail 최소 변경.

Interface / 손댈 후보:
- iris/ui/control_actions/project.py (write_file, run, 공통 ensure helper)
- iris/ui/control_actions/ide.py (open_folder 재사용)
- iris/ui/control_bindings.py 또는 iris/system/ide_link.py (ensure_workspace_aligned)
- iris/runtime/chat_worktree.py (읽기만, 계약 설명)
- iris/ui/_check_ide_workspace_sync.py (신규 권장)
- integrations/hermes-skills/.../iris-vibe-code/SKILL.md (한 줄)

검증 (모두 통과해야 2단계 완료):
A) .venv\Scripts\python.exe -m iris.ui._check_ide_workspace_sync  (또는 동명)
B) .venv\Scripts\python.exe -m iris.system._check_ide_link
C) .venv\Scripts\python.exe -m iris.system._check_iris_ide_bridge
D) 완료 표: 일치/불일치→맞춤성공/맞춤실패 세 경로
E) 단계표 §5.2 완료일·증거 한 줄. 이 프롬프트는 completed/ 로 이동.
F) Phase3 프롬프트는 작성하지 않음(오케스트레이터가 다음 턴에 씀).

Work order:
1. Audit 현재 불일치 가드 호출 지점 표.
2. ensure_iris_ide_workspace(work_root) 한 헬퍼로 모은 뒤 write/run에 연결.
3. 자검 → 버그탐색 → 한국어 보고(구조→증거).
```

## 새 채팅/에이전트에 붙일 한 줄

```text
docs/prompts/Iris-IDE-Phase2-공간동기-구현프롬프트.md 대로 Phase2만 구현·자검·버그탐색. Phase3~5·뇌 Theia 흡수 금지. 커밋 금지.
```
