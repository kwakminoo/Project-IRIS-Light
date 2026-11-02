# 탭→채팅 드래그 첨부 복구 (Bug fix + TDD)

| 항목 | 내용 |
|---|---|
| 모드 | `/poteto-mode` Bug fix + TDD |
| 목표 | IRIS IDE **편집기 탭**에서 Iris 채팅으로 DnD 첨부 복구 (좌측 구조창은 이미 됨) |
| 끝나면 | 비전문가용 **짧은 한국어** 설명 |

## 이미 확인된 사실 (재조사 금지, 런타임으로만 검증)

- 구조창 = `theia-editor-dnd` MIME 패치 → companion HTTP.
- 탭 = Lumino가 HTML5 dragstart 차단 → `onTabPointerDown` + 6px 후 `beginCompanionDrag` + `seedCompanionDragSync`.
- 탭 URI는 `tab.id === shell-tab-${editor.id}` (+ `-hidden`)만. 실패 시 무로그 abort.
- Theia `createTabId` = `'shell-tab-' + title.owner.id` (+ `-hidden`).
- 디스크상 workspace·설치 `bundle.js`에 드래그 마커는 이미 있음 (재시작 여부 확인).
- 자검: `python -m iris.ui.window._check_file_drop`, verify-iris `file-drop`.
- IDE TS 수정 후 `sync_workspace_build` 필수.

## 가설 (증거로 하나씩 탈락)

1. 탭 id ↔ editor.id 불일치
2. pending 시드/레이스/control 신원
3. 조기 finish가 pending 소실
4. 실행 중 IDE가 구 번들

## 금지

- 매 pointerdown `stopPropagation` 재도입 (탭 클릭 회귀)
- pointerdown에서 무조건 “현재 편집기” 폴백 (`bbae0cd` 회귀)
- 커밋/PR (요청 없으면)

## 완료 기준

- 실패하는 자검 → 수정 → 통과
- 구조창 경로 회귀 없음
- 사용자에게 쉬운 한국어 요약
