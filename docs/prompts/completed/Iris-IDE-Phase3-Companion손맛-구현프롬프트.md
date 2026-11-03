# Prompt: IRIS IDE Phase 3 — Companion 손맛 (탭 첨부·터미널·콘솔)

> **상태 (2026-10-28): 구현·자검 완료.** 보관용. 다음 = 단계표 4단계(코딩 깊이) 프롬프트는 오케스트레이터가 작성.

기준 문서:

- `docs/code-review/Iris-IDE-커서조작-일체화-단계표.md` §5.3
- `docs/code-review/IDE-커서처럼-조작-현황.md` §3·§5.3·§5.4·§8 (드래그·터미널·콘솔)
- Phase1·2 완료본: `docs/prompts/completed/Iris-IDE-Phase1-정직화-구현프롬프트.md`, `…Phase2-공간동기-…`

4~5단계(진단/심볼 깊이·셸 브랜드 대규모)와 뇌 Theia 흡수 **금지**. Phase1·2 계약 회귀 금지.

```text
Context:
- Companion: IRIS IDE(WebEngine) 80% + Iris Qt 20%. 탭→채팅 첨부는 OS OLE가 아니라
  포인터 흉내 + HTTP chat.drag_start/end.
- 알려진 끊김: beginCompanionDrag 가 await 없이 askIris → 빠른 드롭 시
  _pending_ide_drag 비어 Iris 위 MouseButtonRelease 가 첨부 못 함.
- 콘솔 깜빡임: tesseract/git/Theia 터미널 ConPTY 기동. no-console-windows 계약.
- 터미널: ensureTerminal 새 기동이 Windows에서 자주 멈춤. 가능하면 기존 터미널 재사용.
- 타일: ide-companion-tile-8020 (정수 8:2, seam overlap 금지).

Goal (이 채팅에서 3단계만):

1) 탭→채팅 첨부
   - pointermove(또는 드래그 시작) 시점에 경로가 Iris(_pending_ide_drag)에 도착.
   - 웹뷰 밖(Iris 위) 버튼 업에서도 pending 경로로 첨부.
   - HTTP가 마우스 업보다 늦어도 마지막 경로로 첨부(레이스 닫기).
   - 타일·frameless·0xC0000409 회귀 없음.

2) 콘솔
   - 첨부/OCR/git/브리지 핫패스에서 Cascadia·cmd 깜빡임 경로 감사 후
     no_window_kwargs / windowsHide / CREATE_NO_WINDOW 계약에 맞춤.
   - GUI 에뮬 예외(DETACHED)는 건드리지 않음.

3) 터미널
   - runTerminalCommand / ensureTerminal: 가능하면 기존 Theia 터미널 재사용.
   - 기동 실패를 성공으로 두지 않음(Phase1 정직화 유지).
   - via=bridge_fallback 터미널 성공 재도입 금지.

4) 타일
   - 80:20·tiles_are_flush 회귀 없음.
   - .venv\Scripts\python.exe -m iris.ui._check_iris_ide_companion_tile

5) 자검
   - 드래그 레이스/ pending 선도착 assert (기존 _check_file_drop 확장 또는 신규).
   - unittest tests.test_no_console_window (해당 변경 시).
   - Phase1·2 자검 회귀: _check_ide_link, _check_iris_ide_bridge, _check_ide_workspace_sync.

Constraints:
- Phase4 LSP·버퍼 깊이, Phase5 시작화면/NOTICE 대규모 금지.
- 에이전트 루프 Theia 흡수 금지.
- TILE_SEAM_OVERLAP / place_qt→SetWindowPos 재도입 금지.
- 커밋 금지(사용자 요청 전). 인라인 import 금지.

Interface / 손댈 후보:
- integrations/iris-ide/src/browser/iris-ide-frontend-contribution.ts (드래그)
- iris/ui/window/main_window.py (_pending_ide_drag, eventFilter, _finish_ide_companion_drag)
- integrations/iris-ide/src/browser/iris-ide-bridge-poller.ts (ensureTerminal)
- iris/system/content_extract.py / win_subprocess (OCR 콘솔)
- iris/ui/_check_file_drop.py 또는 신규 체크
- sync_workspace_build (TS 수정 시 필수)

검증:
A) 드래그/첨부 자검 통과
B) -m iris.ui._check_iris_ide_companion_tile
C) Phase1·2 자검 회귀
D) TS 수정 시 sync_workspace_build + 설치본에 드래그 마커
E) 단계표 §5.3 완료·프롬프트 completed/ 이동. Phase4 프롬프트는 쓰지 않음.

Work order:
1. 드래그 레이스부터(가장 체감). 2. 터미널 재사용. 3. 콘솔 누수. 4. 타일 자검.
```

## 에이전트 한 줄

```text
docs/prompts/Iris-IDE-Phase3-Companion손맛-구현프롬프트.md 대로 Phase3만. Phase4~5·뇌 Theia 금지. 커밋 금지.
```
