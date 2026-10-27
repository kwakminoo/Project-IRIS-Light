# IRIS IDE = 커서처럼 조작 + 작업대 일체화 — 단계표

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-1027-IDE-STAGES |
| 작성일 | 2026-10-27 |
| 관련 | `IDE-커서처럼-조작-현황.md`, Iris Agent Hermes 경로(뇌는 별도) |
| 대상 | IRIS IDE(Theia 기반 작업대) + Companion + Iris Agent IDE 도구 |
| 목적 | 단계별 완료 기준을 고정하고, 단계마다 새 채팅·프롬프트로만 구현한다 |

## 1. 결론

뇌(Iris Agent)는 Theia에 넣지 않는다.  
Theia는 엔진으로 남기고, **조작 계약·배포·이름·수명**을 Iris가 쥐어 IRIS IDE 작업대로 만든다.  
진행은 아래 단계 순서만. 한 단계 검증·버그탐색이 끝나기 전에 다음 프롬프트를 쓰지 않는다(작성 예외: 이 표와 1단계 프롬프트).

## 2. 비목표 (전 단계 공통)

| 하지 않음 | 이유 |
|---|---|
| 에이전트 루프를 Theia/`@theia/ai-*`로 흡수 | 뇌 이중화. Iris Agent 경로와 충돌 |
| Companion 폐기·IDE 단일 창 피벗 | 위키·메일·타일 제품과 별 에픽 |
| Code OSS/Cursor 엔진 교체 | Theia 천장이 입증되기 전 premature |
| 단계 건너뛰어 인라인 완성·코드베이스 색인 | 5단계 이후 선택 |

## 3. 구조 (고정)

```
말 → Iris Agent → IDE/project 도구 → 브리지·폴러 → IRIS IDE(Theia) 화면
클릭 → Iris Qt (에이전트 턴 없음)
Companion → IDE 80% + Iris 20% (별 프로세스)
```

| 층 | 주인 | 이번 에픽에서 |
|---|---|---|
| 뇌 | Iris Agent | 건드리지 않음(도구 계약만 소비) |
| 얼굴 | Qt | Companion 손맛(3단계)만 |
| 작업대 | IRIS IDE | 1~5단계의 주 대상 |

## 4. 단계 요약

| 단계 | 이름 | 한 줄 | 프롬프트 |
|---|---|---|---|
| 1 | 정직화 | 도구 성공 = 디스크·탭·저장의 실측 | ✅ `docs/prompts/completed/Iris-IDE-Phase1-정직화-구현프롬프트.md` (2026-10-28) |
| 2 | 공간 동기 | 에이전트 작업 폴더 = IDE가 연 폴더 | ✅ `docs/prompts/completed/Iris-IDE-Phase2-공간동기-구현프롬프트.md` (2026-10-28) |
| 3 | Companion 손맛 | 탭 첨부·터미널·콘솔가 자연스러움 | ✅ `docs/prompts/completed/Iris-IDE-Phase3-Companion손맛-구현프롬프트.md` (2026-10-28) |
| 4 | 코딩 깊이 | 진단·심볼·버퍼 패치를 믿을 수 있음 | 완료 (2026-10-28) |
| 5 | 셸 일체화 | 사용자는 Theia를 모른 채 IRIS IDE만 씀 | ✅ `docs/prompts/completed/Iris-IDE-Phase5-셸일체화-구현프롬프트.md` (2026-10-28) |
| 6 | (선택) Cursor 고급 | 색인·인라인 완성 등 | 별 에픽 |

## 5. 단계별 완료 기준표

### 1단계. 정직화

| 항목 | 완료 기준 | 상태 (2026-10-28) |
|---|---|---|
| open/create | `openFile` 타임아웃·미폴러를 성공으로 위장하는 경로 0. `bridge_fallback` 문자열·동작 재도입 금지 | 완료. 내장 서버 `opened:true` 제거 |
| visible | `project.write_file` / `ide.open_file` 의 `visible: true` 는 폴러 실측 성공만 | 유지(`iris_ide_editor_opened`) |
| save | 편집기 저장 실패를 `{ saved: true }` 디스크 위장으로 끝내지 않음 | 완료. disk-only → 오류 + `iris_ide_save_ok` |
| 자검 | 회귀 테스트/체크 모듈이 “가짜 성공 → fail”을 고정 | `_check_ide_link` + `_check_iris_ide_bridge` |
| 번들 | IDE 소스 수정 시 `sync_workspace_build` + 설치본 마커 확인 | 완료 |
| 제품 문구 | 사용자 오류에 “Theia” 대신 “IRIS IDE” (NOTICE·라이선스 제외) | 폴러/터미널 오류 문구 정리 |

**증거:** `python -m iris.system._check_ide_link` · `_check_iris_ide_bridge` · `_check_iris_ide_window` · `_check_ide_request_tools` · `sync_workspace_build`  
**프롬프트:** `docs/prompts/completed/Iris-IDE-Phase1-정직화-구현프롬프트.md`

**나가면 안 되는 것:** worktree 자동 전환(2), 드래그(3), LSP 깊이(4).

### 2단계. 공간 동기

| 항목 | 완료 기준 | 상태 (2026-10-28) |
|---|---|---|
| 일치 | `work_root_for` 결과 ≠ 열린 IDE 폴더면 쓰기 전 `ide.open_folder`(또는 동등)로 맞춤 | 완료. `ensure_iris_ide_workspace` → `_open_ide_folder` |
| 거절 | 맞추기 실패 시 침묵 거절 금지. 도구 결과에 원인·필요 폴더 | 완료. `project_root`/`bound_workspace_root`/`open_folder_path`/`error` |
| worktree | 대화 worktree 생성 후 IDE가 그 루트를 연 뒤에만 write/run | 완료. write/run이 맞춤 성공 후에만 진행 |
| 자검 | 불일치·전환·거절 시나리오 assert | 완료. `_check_ide_workspace_sync` 세 경로 |

**증거:** `python -m iris.ui._check_ide_workspace_sync` · `_check_ide_link` · `_check_iris_ide_bridge` (2026-10-28)  
**프롬프트:** `docs/prompts/completed/Iris-IDE-Phase2-공간동기-구현프롬프트.md`

**나가면 안 되는 것:** 드래그 UX, 진단 엔진.

### 3단계. Companion 손맛

| 항목 | 완료 기준 | 상태 (2026-10-28) |
|---|---|---|
| 탭→채팅 | 포인터 이동 시점에 경로가 Iris에 도착. 웹뷰 밖 업에서도 첨부 | 완료. `seedCompanionDragSync`(sync XHR) + Iris 위 release/`drag_end` paths |
| 콘솔 | 첨부·OCR·git·터미널 기동에서 Cascadia/cmd 깜빡임 없음(`no_window` 계약) | 완료. tesseract `no_window` 유지 + 브리지 git `windowsHide` |
| 터미널 | 가능하면 기존 Theia 터미널 재사용. 실패를 성공으로 두지 않음 | 완료. `currentTerminal`/`lastUsedTerminal` 재사용. `bridge_fallback` 금지 |
| 타일 | 80:20·seam 계약 회귀 없음 | 완료. `_check_iris_ide_companion_tile` |

**증거:** `python -m iris.ui.window._check_file_drop` · `_check_iris_ide_companion_tile` · `_check_ide_link` · `_check_iris_ide_bridge` · `_check_ide_workspace_sync` · `unittest tests.test_no_console_window` · `sync_workspace_build`  
**프롬프트:** `docs/prompts/completed/Iris-IDE-Phase3-Companion손맛-구현프롬프트.md`

**나가면 안 되는 것:** 심볼/디버그 신규 기능.

### 4단계. 코딩 깊이

| 항목 | 완료 기준 | 상태 (2026-10-28) |
|---|---|---|
| 진단 | 미수집과 “문제 0개” 구분(`reported`/`queried` 등). 빈 성공 금지 | 유지. `reported` false ≠ clean; `_diagnostics_snapshot` |
| 심볼·위치 | 폴러→Theia 서비스 실호출. 실패는 실패 | 완료. `queried` 필수 (`iris_ide_query_ok`) |
| 버퍼 | 선택 치환·insert가 Monaco 기준. 디스크 끝붙이기 폴백은 명시 실패 또는 별 플래그 | 완료. selection/insert/apply disk 폴백 제거 + `iris_ide_edit_ok` |
| 스킬 | vibe/코딩 스킬이 위 도구를 “있을 때만” 안내 | 완료. vibe + hermes_memory_nudge 한두 줄 |

**증거:** `python -m iris.system._check_ide_link` · `_check_iris_ide_bridge` · `_check_ide_workspace_sync` · `iris.ui.window._check_file_drop`  
**프롬프트:** `docs/prompts/completed/Iris-IDE-Phase4-코딩깊이-구현프롬프트.md`

**나가면 안 되는 것:** 코드베이스 벡터 색인, 탭 완성 모델.

### 5단계. 셸 일체화 (작업대 제품)

| 항목 | 완료 기준 | 상태 (2026-10-28) |
|---|---|---|
| 이름 | 창·시작 화면·메뉴에 IRIS IDE. 일상 UI에 Theia 노출 0(NOTICE 제외) | 완료. 설정·로딩·토스트·설치 안내 Theia→IRIS IDE. `iris.ui._check_iris_ide_branding` |
| 기동 | Iris 경로로만 IDE 기동·동기화. 사용자가 theia CLI를 몰라도 됨 | 완료. `shared_iris_ide_runtime` docstring 한 줄 |
| 수명 | Companion 종료/복귀 정책이 문서+코드로 한 줄. 고아 창 없음 | 유지. `_check_ide_companion_windows` |
| 고지 | LICENSE/NOTICE에 Theia(EPL 등) 기반만 | 확인. LICENSE.md §6 · THIRD_PARTY_NOTICES |

**증거:** `python -m iris.ui._check_iris_ide_branding` · `_check_ide_companion_windows` · `_check_iris_ide_window` · `_check_ide_link` · `_check_ide_workspace_sync` · `_check_iris_ide_bridge`  
**프롬프트:** `docs/prompts/completed/Iris-IDE-Phase5-셸일체화-구현프롬프트.md`

**나가면 안 되는 것:** 엔진 포크 대규모, AI 플러그인.

### 6단계. (선택) Cursor 고급

별 에픽. 기준은 이 문서에 잠정만 둔다: 색인·@코드·인라인 완성은 **Iris Agent + IDE API**. Theia 내 두 번째 뇌 금지.

## 6. 진행 규칙 (채팅 운영)

1. **이 채팅(또는 문서 채팅):** 단계표 + **다음 미완 단계** 프롬프트만 작성.  
2. **새 채팅:** 해당 프롬프트만 붙여 구현 → 자검·수동 검증 → 버그 탐색·수정.  
3. 단계 완료 시: 프롬프트·관련 현황을 `docs/prompts/completed/`, `docs/code-review/completed/`로 이동(`archive-finished-reports`).  
4. **그다음** 문서 채팅에서 N+1 프롬프트 작성 → 다시 새 채팅 구현.  
5. 커밋은 사용자 요청 시에만.

## 7. 차용 (전 단계)

| 이름 | 가져올 부분 | 안 가져옴 |
|---|---|---|
| 현황 보고서 개선안 §8 | 정직화·worktree·드래그·콘솔 항목 | 한 번에 전부 구현 |
| Hermes→Iris Agent 일체화 | 소유권·이름·NOTICE 패턴 | 루프를 IDE에 흡수 |
| Theia EditorManager/Terminal | 폴러 실호출 | Theia AI Agent |
| nabheet ide-mcp 목록 | 4단계 체크리스트 | VSIX 통째 이식 |

## 8. 조치

1. 1~5단계 1차 완료 (2026-10-28). “커서처럼 조작 + Iris IDE 셸 일체화” 1차 완료.  
2. 통과 증거는 각 단계 §5.x 증거 행·`docs/prompts/completed/` 프롬프트.  
3. 6단계는 별도 요청으로만 연다. Phase6 프롬프트는 이 표에서 쓰지 않음.
