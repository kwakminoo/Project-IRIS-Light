# Prompt: IRIS IDE Phase 4 — 코딩 깊이 (진단·심볼·버퍼)

기준:

- `docs/code-review/Iris-IDE-커서조작-일체화-단계표.md` §5.4
- `docs/code-review/IDE-커서처럼-조작-현황.md` (진단·버퍼)
- Phase1~3 completed 프롬프트. 회귀 금지.

5단계(셸 브랜드 대규모)·뇌 Theia 흡수·코드베이스 색인/인라인 완성 **금지**.

```text
Context:
- ide.diagnostics 는 reported false vs 빈 목록 구분이 이미 요약에 있음. 빈 성공 위장 재발 막기.
- ide.symbols / references / definition 은 폴러→Theia. 실패·미수집을 성공처럼 두지 말 것.
- ide.edit: standalone-bridge 가 폴러 실패/noEditor 시 diskEdit 으로 파일 끝 append
  (via=disk, applied=append). 선택 치환이 아닌데 에이전트가 “고쳤다”고 말할 수 있음.
- Phase1 save 와 같이: 버퍼 편집 계약은 via=editor 만 ok.

Goal (4단계만):

1) 버퍼 편집 정직화
   - replaceSelection / insertText / applyTextEdit: 폴러·편집기 실패 시 diskEdit 폴백 금지.
     hard error (HTTP/예외).
   - replaceRange: project.write_file 전체 치환용 disk 허용은 유지해도 됨.
     단 ide.edit op=replace_range|selection|insert 는 via=editor 가 아니면 액션 실패.
   - iris_ide_edit_ok(bridge_out) 헬퍼(또는 동등) + ide.edit 에 연결.
   - _check_iris_ide_bridge: 프론트 없이 replace_selection 이 성공하면 fail.

2) 진단
   - getDiagnostics: reported false 와 diagnostics=[] 구분 유지·자검.
   - reported false 를 “문제 없음”으로 ok 포장하는 경로 있으면 제거.

3) 심볼·참조·정의
   - 폴러 타임아웃/미지원은 오류. 빈 items + queried true 만 “없음”.
   - queried/via 필드가 없으면 스킬·요약이 말하도록 최소 보강.

4) 스킬
   - iris-vibe-code / hermes_memory_nudge: 버퍼=via editor, disk append≠선택 치환,
     diagnostics reported 규칙 한두 줄(대규모 개편 금지).

5) 자검
   - Phase1~3 회귀: _check_ide_link, _check_iris_ide_bridge, _check_ide_workspace_sync,
     _check_file_drop(또는 window._check_file_drop).
   - edit 정직화 assert 추가.
   - TS 수정 시 sync_workspace_build.

Constraints:
- Phase5 시작화면/NOTICE/창 이름 대규모 금지.
- Theia AI·색인·탭 완성 금지.
- Companion 타일·new-window·no-console 계약 유지.
- 커밋 금지. 인라인 import 금지.

Interface:
- integrations/iris-ide/bridge/standalone-bridge.js (diskEdit 폴백 범위)
- iris/ui/control_bindings.py (iris_ide_edit_ok)
- iris/ui/control_actions/ide.py (ide.edit)
- iris/system/_check_ide_link.py / _check_iris_ide_bridge.py
- integrations/hermes-skills/.../iris-vibe-code/SKILL.md

검증:
A) edit disk-append 거절 자검
B) diagnostics reported 자검(기존 또는 보강)
C) Phase1~3 회귀 자검
D) 필요 시 sync_workspace_build
E) 단계표 §5.4 완료·프롬프트 completed/. Phase5 프롬프트 쓰지 않음.
```

## 에이전트 한 줄

```text
docs/prompts/Iris-IDE-Phase4-코딩깊이-구현프롬프트.md 대로 Phase4만. Phase5·뇌 Theia 금지. 커밋 금지.
```
