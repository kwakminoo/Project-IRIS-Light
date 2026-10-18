# 아이리스가 커서 IDE처럼 IRIS IDE를 다루는가

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-REV-2026-1013-01 |
| 작성일 | 2026-10-13 |
| 관련 | IRIS-REV-2026-1003-04 (IDE 컨트롤 현황). 그 이후 브리지가 편집·진단·디버그를 Theia로 넘기도록 바뀌었다. |
| 대상 | IDE Companion에서 이미지 첨부·채팅 전송·탭 드래그·파일 생성·화면 표시 |
| 목적 | 지금 끊긴 세 증상과, 커서가 IDE를 다루는 수준까지 남은 빈 자리를 한 문서에 둔다. |
| 조사 | 소스. 실행 중인 IDE에서 재현하지 않았다. 설치본 `bundle.js`와 소스의 일치도 확인하지 않았다. |

## 1. 결론

채팅에 코드가 보이는 것과, IDE 탭에 파일이 생기는 것은 다른 경로다. 사진에서 코드를 뽑아 디스크에 쓰고 탭을 여는 파이프는 꺼져 있고, 모델이 `project.write_file`을 성공시키기 전에는 파일이 없다. 써도 IRIS IDE 분기는 편집기가 열렸는지 보지 않고 `visible: true`를 돌려 준다. 실행은 터미널 명령이라 탭이 없어도 돌아간다.

탭을 채팅으로 끌어 첨부하는 경로는 OS 드롭이 아니다. WebEngine 안의 포인터가 놓이기 전에 Iris가 경로를 받지 못하면, Iris 위에서 마우스를 떼도 칩이 생기지 않는다.

이미지를 붙이거나 그 턴을 보내면 글자 추출이 `tesseract.exe`까지 내려갈 수 있다. 이 실행 파일은 콘솔 프로그램이라 숨김이 실패하면 창이 생겼다가 사라진다. 코드를 돌릴 때는 Theia 통합 터미널이 Windows ConPTY로 셸을 새로 띄우고, 그 기동이 실패하거나 명령이 바로 끝나면 같은 깜빡임으로 보인다.

커서처럼 한 프로세스 안에서 편집기·색인·진단을 붙잡고 고치는 구조는 아니다. Hermes가 HTTP로 액션을 부르고, Theia 프런트 폴러가 그중 일부만 화면에 반영한다.

## 2. 확인한 사실

| 사실 | 근거 |
|---|---|
| 사진→파일 파이프는 호출부에서 항상 통과시킨다. | `MainWindow._handle_image_code_pipe`가 `return False` |
| 답변 코드블록으로 파일을 만드는 폴백은 턴 시작 때 비운다. | `_commit_recorded_user_turn_bound`가 `_pending_local_vibe_prompt = ""` |
| 파일 생성은 `project.write_file` 성공뿐이다. | 같은 함수 주석. `settle_completion_claim`은 완료 문장으로 쓰지 않는다. |
| 쓰기 루트는 대화마다 git worktree로 바뀔 수 있다. | `work_root_for`. 첫 대화는 본 체크아웃, 다음 대화는 `*.iris-worktrees/chat-<id>` |
| 그 루트가 열린 IDE 폴더와 다르면 쓰기도 실행도 거절한다. | `project.write_file` / `project.run`의 workspace 불일치 오류 |
| IRIS IDE에 쓴 뒤에는 탭 확인 없이 보였다고 답한다. | `via: iris_ide_bridge`, `visible: True` 고정 |
| 편집기 열기 대기가 실패해도 열린 것으로 반환할 수 있다. | `standalone-bridge.js` `openFile`의 `via: bridge_fallback` |
| 실행은 디스크 명령이고 기본으로 터미널을 연다. | `project.run`의 `reveal_terminal` 기본값 True. 정적 HTML만 브라우저 |
| 탭 드래그는 HTML5 `dragstart`가 막혀 포인터로 흉내 낸다. | `installComposerDragBridge` 주석. Lumino `preventDefault` |
| 첨부는 커서가 Iris `frameGeometry` 안일 때만 한다. | `_finish_ide_companion_drag` |
| 이미지 턴은 비전 다음 OCR이다. | `AttachmentWorker` → `_ocr_image` → `_ocr_png_bytes` |
| Tesseract 콘솔 깜빡임은 이미 알려진 결함이다. | `content_extract._hide_tesseract_console` 주석 |
| Theia에서 터미널을 새로 띄우는 일은 Windows에서 자주 멈춘다. | `ensureTerminal` 주석. ConPTY |

## 3. 이번 증상

| 증상 | 갈라지는 곳 | 결과 |
|---|---|---|
| 사진 속 코드는 채팅에 있는데 파일이 없다 | `_handle_image_code_pipe`가 끄고, 바이브 프롬프트를 비운 뒤, 모델이 도구를 성공시키지 않음. 또는 worktree와 IDE 폴더가 달라 쓰기가 거절됨 | 추출 문장만 남음 |
| 파일은 실행되는데 편집기에 안 뜬다 | `create_file`은 디스크. `open_file`은 폴러 3.5초 실패 시 `bridge_fallback`. 반환은 `visible: true`. `project.run`은 그 파일로 셸을 보냄 | 터미널 출력은 있고 탭은 없음 |
| 탭을 채팅으로 끌어도 첨부가 안 된다 | 탭 `pointerup`/`dragend`는 WebEngine 안에 남음. `chat.drag_start`는 비동기. Iris 쪽 `MouseButtonRelease`는 pending이 이미 있을 때만 첨부 | 칩 없음 |
| 첨부하거나 보내면 터미널이 깜빡인다 | 이미지 턴의 `tesseract.exe`. 실행 턴의 `newTerminal`+ConPTY. 대화 루트 계산의 `git` | 창이 생겼다가 닫힘 |

## 4. 구조

세 요청은 채팅까지는 같고, 그 다음이 갈라진다.

```
이미지 첨부 (칩만)
  → ChatPanel.attach_drop_paths
  → 칩. 이 단계에서는 파일을 만들지 않음

채팅 전송 + 첨부
  → MainWindow._on_user_text
  → _commit_recorded_user_turn_bound
      → _handle_image_code_pipe          … 항상 False (여기서 파일로 가지 않음)
      → _pending_local_vibe_prompt = ""  … 코드펜스 폴백 꺼짐
      → AttachmentWorker
          → _current_project_root → work_root_for → git
          → page_vision.transcribe_images
          → 글자가 짧으면 content_extract._ocr_png_bytes → tesseract.exe
      → Hermes iris_invoke
          → project.write_file
              → work_root_for
              → IDE 폴더와 같으면
                  IRIS IDE: bridge createFile(디스크) + openFile(프런트 큐)
                  그 외 IDE: 빈 파일 → open_file_in_workspace → 스트림
              → 다르면 오류, 파일 없음
          → project.run
              → IRIS IDE: runTerminalCommand → 폴러 ensureTerminal → ConPTY
      → 턴 끝 _try_reveal_local_vibe_code
          → 프롬프트가 비어 있으면 즉시 return

탭 → 채팅 첨부
  → iris-ide-frontend-contribution
      pointerdown → (6px 이동) beginCompanionDrag
      → POST /v1/invoke chat.drag_start     … 응답 전에 마우스가 떨어질 수 있음
      → MainWindow._pending_ide_drag
  → 마우스 업
      WebEngine 안이면 onTabPointerUp → chat.drag_end
      Iris 위이면 Qt MouseButtonRelease → _finish_ide_companion_drag
          frameGeometry에 커서가 있을 때만 _chat.attach_drop_paths
  → OS OLE text/uri-list 는 QWebEngine 경계를 거의 넘지 않음 (이 경로의 전제)
```

갈라지는 곳 세 개.

1. 사진 파이프와 바이브 폴백을 꺼 둔 줄. 모델 도구만 파일을 만든다.
2. `openFile` 실패를 성공으로 바꾸는 `bridge_fallback`, 그리고 `visible: true` 고정.
3. 탭 제스처의 끝이 WebEngine 안에 있고, Iris는 HTTP가 도착한 뒤에만 버튼을 뗀 것을 본다.

## 5. 코드 리뷰

### 5.1 사진에서 파일까지 — 한 일, 못 막은 이유

`file_write_claim.apply_image_code_pipe`는 글자를 뽑아 `write_file`을 호출할 수 있다. `MainWindow._handle_image_code_pipe`는 그 함수를 부르지 않고 `False`만 반환한다. 주석은 키워드로 턴을 가로채지 않겠다는 뜻이다. 그래서 채팅에 코드가 있어도 디스크 쓰기로 내려가지 않는다.

`_commit_recorded_user_turn_bound`는 이어서 `_pending_local_vibe_prompt`를 빈 문자열로 둔다. `_try_reveal_local_vibe_code`는 프롬프트가 없으면 돌아간다. 도구가 이미 썼다고 표시된 턴도 여기서 멈춘다. 사후에 탭을 열어 주는 자리가 없다.

### 5.2 쓰기와 화면 — 한 일, 못 막은 이유

`project.write_file`은 `work_root_for`로 루트를 바꾼 뒤, 바인딩된 `session.workspace_root`와 같아야 쓴다. 두 번째 대화는 worktree를 만들고, 이미 열린 IDE는 첫 폴더에 남을 수 있다. 그때 쓰기는 오류다. 모델이 채팅에 코드를 보여 준 것과는 별개다.

IRIS IDE이고 폴더가 같으면 `create_file`로 디스크에 쓰고 `open_file`을 큐에 넣는다. 반환 딕셔너리의 `visible`은 참이다. 폴러가 3.5초 안에 `openInEditor`를 끝내지 못하면 브리지는 `opened: true, via: bridge_fallback`이다. 탭이 없어도 도구 결과는 성공이다.

`project.run`은 그 다음 셸이다. 파일이 디스크에 있으면 편집기 없이 실행된다. 기본 `reveal_terminal`이 참이라 터미널을 연다.

다른 IDE 분기는 빈 파일을 만들고 `open_file_in_workspace`로 제목 표시를 기다린다. 열리지 않으면 오류를 반환한다. IRIS IDE 분기만 그 확인이 없다.

### 5.3 탭 드래그 — 한 일, 못 막은 이유

`installComposerDragBridge`는 OS 드롭이 WebEngine을 넘지 못하는 전제로 만들어졌다. 탐색기 드래그는 `DataTransfer.setData('theia-editor-dnd')`를 가로채 `chat.drag_start`를 보낸다. 탭은 Lumino가 `dragstart`를 막아서 `pointerdown`/`pointermove`로 `draggable`을 켠다.

`beginCompanionDrag`는 `await` 없이 `askIris`를 던진다. `onTabPointerUp`과 `dragend`는 문서 안에 있다. 포인터가 IDE 웹뷰를 벗어나 Iris 위에서 놓이면, 그 두 이벤트는 페이지에 안 올 수 있다. Qt `eventFilter`의 `MouseButtonRelease`가 첨부를 대신하는데, `_pending_ide_drag`가 비어 있으면 아무것도 하지 않는다. 빠른 드롭은 HTTP보다 마우스 업이 먼저다.

`_finish_ide_companion_drag`는 `frameGeometry().contains(QCursor.pos())`가 거짓이면 경로만 20초 보관한다. 웹뷰 안에서 일찍 `pointerup`이 오고 커서가 아직 IDE에 있으면 첨부를 미룬다. 이후 Iris 릴리즈가 이 pending을 못 보면 칩은 없다.

`_active_workspace_iris_panel`은 항상 `None`이다. 첨부는 `self._chat`으로 간다. Companion에서 보이는 컴포저가 그 패널이면 칩은 거기에 붙는다. 막히는 지점은 패널이 아니라 제스처가 HTTP에 닿기 전이다.

실행본 번들(`~/.iris-light/runtimes/iris-ide/lib/frontend/bundle.js`)이 이 소스를 포함하지 않으면 탭 리스너 자체가 없다. 이번 조사는 번들 문자열을 대조하지 않았다.

### 5.4 터미널이 깜빡이는 쪽 — 한 일, 못 막은 이유

이미지 턴은 `AttachmentWorker`가 비전으로 읽고, 글자가 8자 미만이거나 실패하면 `_ocr_png_bytes`가 `tesseract.exe`를 띄운다. `_hide_tesseract_console`은 pytesseract의 `subprocess_args`에 `CREATE_NO_WINDOW`와 `SW_HIDE`를 넣는다. 주석은 `SW_HIDE`만으로는 창이 깜빡인다고 적혀 있다. 훅이 적용되기 전의 `get_tesseract_version`, 또는 훅을 타지 않는 실행은 콘솔이 그대로다.

채팅이 `project.run`으로 가면 폴러 `ensureTerminal`이 터미널을 만들고 `start()`를 기다린다. 주석은 Windows ConPTY에서 이 시작이 자주 멈춘다고 적는다. 실패한 기동은 콘솔 호스트가 나타났다가 사라지는 형태로 남는다. 짧은 파이썬 스크립트는 패널이 열린 뒤 프로세스가 바로 끝난다.

`work_root_for`의 git은 `no_window_kwargs()`를 쓴다. 브리지 `getGitStatus` / `getGitDiff`의 `execSync`는 `windowsHide`가 없다. 파이썬 클라이언트에서 `get_git_status`를 부르는 곳은 메서드 정의뿐이다. 매 전송의 깜빡임 원인으로 보지 않는다.

IDE 프로세스 기동은 `CREATE_NO_WINDOW`만 있고 `STARTUPINFO`/`SW_HIDE`는 없다. worktree로 워크스페이스를 다시 띄우면 node 콘솔이 한 번 더 스칠 수 있다.

### 5.5 하지 않은 일

- 켜 둔 IDE에서 이미지 첨부, 전송, 탭 드래그를 다시 눌러 보지 않았다.
- 설치본 번들에 `onTabPointerUp` / `chat.drag_start`가 있는지는 보지 않았다.
- Tesseract 창을 이번 세션에서 캡처하지 않았다.
- Monaco 자동완성, 인라인 편집, 시맨틱 색인을 Iris에 붙이지 않았다.

## 6. 커서 IDE와 IRIS IDE

커서는 편집기와 에이전트가 한 제품이다. 아이리스는 채팅 프로세스가 Theia를 HTTP와 파일로 미는 구조다. Theia 1.74가 이미 가진 편집기·언어·태스크·디버그를 폴러가 일부 호출한다.

| 기능 | 커서 IDE | IRIS IDE 지금 | 판단 |
|---|---|---|---|
| 폴더 열기, 컴패니언 배치 | 워크스페이스가 곧 창 | `ide.open_folder`, 8:2 타일 | 됨. 두 번째 대화 worktree는 열린 창과 어긋날 수 있음 |
| 채팅에 파일·이미지 첨부 | 컴포저가 편집기와 같은 프로세스. 탭 드래그가 곧 컨텍스트 | 탐색기 MIME 가로채기, 탭은 포인터 흉내, 이미지는 칩 후 워커 | 탐색기 경로는 있음. 탭은 경계에서 끊김 |
| 이미지에서 코드 추출 | 모델이 이미지를 보고 패치를 적용 | 비전·OCR로 글자를 읽음. 파일 쓰기는 도구 성공에 맡김 | 읽기는 됨. 저장·탭은 별도 |
| 파일 생성·수정 | 버퍼 패치, 체크포인트 | 디스크 `createFile` / `replaceRange`. 버퍼 편집은 폴러 `editBuffer`가 있을 때 | 디스크는 됨. 탭 반영은 폴러 성공에 종속 |
| 실행·터미널 | 통합 터미널 도구, 출력 수집 | `runTerminalCommand`가 키 입력을 보내고 `.iris/last_run.log`의 `IRIS_EXIT:`를 읽음 | 됨. ConPTY 기동이 불안정 |
| 진단·심볼·정의 | 언어 서버를 에이전트가 읽음 | 폴러 `querySymbols` / `queryLocations` / 마커. `reported: false`면 미수집 | 소스에는 연결됨. 빈 성공과 미수집을 스킬이 구분하라고 적음 |
| 저장·선택 영역 | 버퍼 저장, 선택 치환 | `saveOne`은 편집기 `save`. 폴러가 없으면 디스크 폴백. `insertText` 디스크 폴백은 끝에 붙일 수 있음 | 폴러가 살아 있을 때만 버퍼 |
| 디버그·태스크 | 브레이크포인트, launch | `startDebug` / `runNamedTask`가 Theia 서비스를 호출 | 소스에는 연결됨. 세션 설정이 없으면 시작 실패가 맞다 |
| 확장 | 마켓플레이스, 즉시 호스트 | VSIX를 `deployedPlugins`에 풀고 프로세스를 재기동 | 설치는 됨. 핫 리로드 없음 |
| 색인·@코드·탭 완성 | 코드베이스 색인, 인라인 완성 | 프로젝트 파일 나열·읽기. 완성 엔진 없음 | 안 됨 |
| 멀티 에이전트 작업 트리 | 클라우드·워크트리 체크아웃을 그 창에 염 | 메모리 표 + `git worktree add`. IDE가 그 폴더로 따라가지 않으면 쓰기 거절 | 반만 됨 |
| 깃 상태 | 소스 컨트롤 뷰와 에이전트 | 브리지가 `git status`를 실행. 뷰와 동기 아님 | 디스크 기준만 |

2026-10-03 보고서가 적었던 빈 성공(`getDiagnostics` 항상 `[]`, `saveFile`이 저장 없이 `saved: true`, 디버그 `hooked: true`)은 지금 소스의 `iris-ide-bridge-ops.ts`와 `standalone-bridge.js`에서 프런트 호출로 바뀌어 있다. 설치본 번들이 그 소스와 같아야 실행도 같다.

## 7. 보안

| 지점 | 내용 |
|---|---|
| 컨트롤 토큰 | Theia 페이지가 `Authorization: Bearer`로 `127.0.0.1` `/v1/invoke`를 호출한다. 페이지 안 스크립트는 첨부·폴더 열기·쓰기를 같은 토큰으로 할 수 있다. |
| 터미널 | `project.run` 명령은 모델이 고른 문자열이다. 통합 터미널에서 돈다. `execSync`로 브리지가 대신 실행하는 폴백은 막아 두었다. |
| 경로 | `resolve_under_root`는 `..`와 루트 밖을 거절한다. worktree로 루트 자체가 바뀌는 것은 이 검사 밖이다. 첫 대화는 본 체크아웃에 쓴다. |
| 성공 위장 | `visible: true`, `bridge_fallback`의 `opened: true`는 모델이 파일을 열었다고 말하게 만든다. 권한 우회는 아니고, 조작 결과 위조다. |
| 깃 | `execSync('git status')`에 `windowsHide`가 없다. 사용자 폴더에서 셸이 한 번 더 뜬다. |
| 첨부 | 이미지·파일 내용은 신뢰하지 않는 입력으로 프롬프트에 넣는다. OCR 실행 파일은 로컬 `tesseract.exe`다. |

## 8. 개선안

1. 사진에서 코드를 파일로 남기는 일은 `_handle_image_code_pipe`가 `apply_image_code_pipe`를 다시 부르거나, 모델 도구 결과가 `ok`이고 디스크에 파일이 있을 때만 완료로 말하는 한쪽으로 모은다. 둘 다 꺼 두면 채팅 추출만 남는다.
2. `project.write_file`의 IRIS IDE 분기는 폴러 `openInEditor`가 `{ opened: true }`이고 `via`가 `bridge_fallback`이 아닐 때만 `visible: true`다. 아니면 오류다.
3. `work_root_for`가 새 폴더를 돌려주면, 그 경로로 `ide.open_folder`가 끝난 뒤에만 쓴다. 열린 창과 다르면 본 트리에 쓰지 않고, 침묵으로 거절하지 않는다.
4. 탭 첨부는 `pointermove`에서 경로를 Iris에 먼저 넣고, Iris 위 버튼 업은 pending이 늦어도 마지막 경로로 첨부한다. `drag_end`가 웹뷰 안에 갇혀도 된다.
5. 이미지 OCR과 git, Theia·node 기동은 `no_window_kwargs()`(또는 브리지는 `windowsHide: true`)만 쓴다. 터미널이 필요할 때는 이미 떠 있는 Theia 터미널에만 입력하고, 실패 시 콘솔 창을 새로 만들지 않는다.
6. 진단·심볼·디버그는 설치본 번들에 `querySymbols` / `startDebug`가 있을 때만 동작으로 친다. 소스만 있고 번들이 오래면 다시 끊긴다.

## 9. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| Theia `EditorManager.open` (`iris-ide-bridge-poller.openInEditor`) | 이미 있는 탭 열기. 성공은 이 반환만 믿는다. | 호출은 연결되어 있다. 브리지가 타임아웃을 성공으로 바꾸는 줄만 빼면 된다. |
| Theia `TerminalService` + node-pty ConPTY | 통합 터미널. `windowsHide`에 해당하는 호스트 창 숨김. | 새 터미널 제품을 만들지 않는다. 기동 실패를 성공으로 두지 않으면 된다. |
| pytesseract `subprocess_args` + `CREATE_NO_WINDOW` | 콘솔 없는 OCR. 코드에 훅이 있다. | 훅 밖 실행이 남는지 실행으로 확인한 뒤에 고친다. |
| Cursor / VS Code 컴포저 드롭 | 편집기와 채팅이 같은 프로세스라 탭 URI가 드롭 데이터다. | QWebEngine 경계를 OLE로 고치지 못한다. 경로를 버튼 업보다 먼저 Iris에 두는 쪽이 그 계약에 가깝다. |
| `git worktree` (이미 `chat_worktree.py`) | 대화마다 체크아웃을 나눈다. | 커서의 워크트리는 그 창의 워크스페이스다. 폴더를 안 바꾸고 쓰기만 돌리면 거절된다. |
| Theia 1.75 `@theia/ai-mcp`, Agent Plugin | IDE 안 에이전트, MCP, 스킬 폴더. | 2026-10-03과 같다. 실행본은 1.74이고, 에이전트는 IDE 밖 Hermes다. |
| `nabheet.vscode-ide-mcp` 도구 목록 | 진단, 호버, 참조, 이름 바꾸기, 브레이크포인트. | 구현 위치는 그 VSIX가 아니라 지금 폴러다. 목록만 체크리스트다. |
| Continue, Cursor 탭 완성 | 인라인 모델. | 이번 빈 자리는 파일 표시와 드래그와 콘솔이다. 완성 모델을 새로 들이지 않는다. |

## 10. 조치

1. 사진 턴은 도구가 파일을 만들었는지 디스크 경로로만 말하고, 채팅의 코드블록을 성공으로 세지 않는다.
2. `openFile`의 `bridge_fallback`은 오류로 바꾸고, `visible`은 폴러 성공에만 붙인다.
3. 대화 worktree를 쓰면 IDE 워크스페이스를 그 폴더로 연 뒤에 쓴다.
4. 탭 드래그는 이동 시점에 `chat.drag_start`를 끝내고, Iris 위 릴리즈가 그 경로를 첨부하게 한다.
5. `tesseract.exe`와 Theia 터미널 기동에 콘솔 창이 남는지 한 번씩 확인한다. 남으면 `no_window_kwargs` / `windowsHide` 밖으로 새는 호출을 막는다.
6. 소스를 고친 뒤에는 `sync_workspace_build`로 설치본 번들을 갱신하고 IDE를 다시 띄운다.
