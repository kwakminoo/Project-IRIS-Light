# 구현 프롬프트: Iris IDE Companion Mode (창 타일 80:20)

> **상태 (2026-08-25): 구현 완료.** 이 문서는 역사적 구현 프롬프트로 보관한다.  
> 현재 사이드바 툴팁은 `"IDE Companion"`, 페이지는 `iris/ui/workspaces/ide_companion_page.py`.  
> Ask/설계 대화(2026-07-23) 합의안 기준.  
> **임베드 금지** — IDE는 별도 창이며, 화면 work area의 약 80% 크기로 **배치**한다.

---

## Context

- 프로젝트: Project-IRIS-Light (PyQt6 HUD)
- AI 백엔드: Hermes gateway + Ollama (이미 연동·자동 기동됨)
- 기존 창 유틸: `iris/automation/window_controller.py` (`list_visible_windows`, `focus_and_place` 등)
- 프로필: `iris/storage/user_profile.py`, `iris/ui/settings/user_profile_dialog.py`
- 사이드바 IDE 아이콘: `main_window.py` — **구현됨** (`"IDE Companion"`)
- Live Activity 로그는 이모지 제거됨 (`activity_privacy.strip_emoji`) — 유지
- 코딩 AI는 **항상 Iris → Hermes → Ollama**. IDE 내장 AI(Cursor Composer 등)를 대체/제어하지 않음. UX 문구만 “바이브코딩은 Iris 채팅으로” 통일.

## Goal

1. 프로필에서 사용할 IDE를 선택 (Cursor / VS Code 등).
2. Iris **IDE 아이콘** 클릭 시:
   - 선택된 IDE를 **별도 창**으로 사용 (없으면 실행, 있으면 **재실행·재시작 금지**, 기존 창 attach).
   - 주 모니터 work area 기준 **IDE ≈ 80% / Iris ≈ 20%** 로 타일 배치.
   - Iris는 **IDE Companion 레이아웃**(슬림 세로 UI)로 전환.
3. Companion 모드에서 IDE 아이콘을 다시 누르면:
   - Iris만 **일반(기본) 레이아웃**으로 복귀.
   - **IDE 창은 닫지 않고 유지**.
4. 일반 모드에서 다시 IDE 아이콘을 누르면:
   - 이미 떠 있는 IDE를 **다시 타일만** (재실행 금지).
5. Companion 모드에서도 채팅/도구는 Hermes+Ollama.

## Constraints

- YAGNI: Monaco/Theia/HWND 임베드/IDE 내장 AI 연동 **금지**.
- Windows 우선. DPI·멀티모니터는 “현재 Iris가 있는 모니터의 work area” 기준.
- 새 의존성 최소화. 기존 `pywin32` / `window_controller` 확장 우선.
- 기존 Hermes 자동 기동·이모지 필터·채팅 경로 깨지 말 것.
- 실패 시 Live Activity에 짧은 영문/한글 텍스트 로그만 (이모지 없음).
- ponytail: 최소 코드. 의도적 단순화는 `ponytail:` 주석.

## IDE 경로 (이 PC 기준 — 하드코딩 기본값 + which 폴백)

### Cursor (설치 확인됨)

| 용도 | 경로 |
|------|------|
| GUI 실행 파일 | `C:\Users\kwakm\AppData\Local\Programs\cursor\Cursor.exe` |
| CLI | `C:\Users\kwakm\AppData\Local\Programs\cursor\resources\app\bin\cursor.cmd` |

폴더 열기 예:  
`cursor.cmd "C:\path\to\project"`  
또는  
`Cursor.exe "C:\path\to\project"`

### VS Code (현재 이 PC에 미설치 — 기본 후보 경로)

설치 시 일반적인 위치 (존재하는 첫 경로 사용):

| 용도 | 경로 |
|------|------|
| GUI | `%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe`  
→ `C:\Users\kwakm\AppData\Local\Programs\Microsoft VS Code\Code.exe` |
| GUI (대안) | `C:\Program Files\Microsoft VS Code\Code.exe` |
| CLI | 같은 설치의 `bin\code.cmd` (보통 PATH의 `code`) |

**주의:** 지금 PATH의 `code.cmd`는 Cursor의 `codeBin` 심(  
`C:\Users\kwakm\AppData\Local\Programs\cursor\resources\app\codeBin\code.cmd`  
)이므로 **VS Code로 취급하지 말 것**. VS Code는 `Microsoft VS Code\Code.exe` 존재 여부로만 판별.

### 해석 우선순위 (런처)

1. 프로필/설정에 저장된 `ide_exe` 경로가 파일이면 그것.
2. 선택 타입이 `cursor` → 위 Cursor.exe → `shutil.which("cursor")`.
3. 선택 타입이 `vscode` → VS Code Code.exe 후보 → (Cursor codeBin 제외) `which("code")`는 신중히.
4. 없으면 에러 메시지 + 프로필에서 경로 수정 유도.

## Interface / 데이터

### UserProfile 확장 (또는 별도 pref 키 `ide_companion_v1`)

```text
preferred_ide: "cursor" | "vscode" | "custom"
ide_exe_path: str          # 비우면 기본 경로 해석
ide_cli_path: str          # 선택, 폴더 열기용
project_root: str          # IDE/Hermes 작업 루트 (비우면 cwd 또는 최근)
```

프로필 UI: 콤보(Cursor / VS Code / 사용자 지정) + 실행 파일 경로 LineEdit + (선택) 프로젝트 루트.

### 모드 상태 (MainWindow)

```text
_ui_mode: "normal" | "ide_companion"
_ide_hwnd: int | None      # attach된 IDE 창
_ide_pid: int | None
```

### 타일 비율

- work area width W, height H (작업 표시줄 제외 — `SystemParametersInfo` SPI_GETWORKAREA 또는 Qt screen availableGeometry)
- IDE: left=0 (또는 work.left), width=int(W*0.8), height=H
- Iris: left=work.left+IDE_width, width=W-IDE_width, height=H
- 오차 1~2px는 IDE에 몰아도 됨

### Companion Iris UI (오른쪽 ~20%)

좌우 세로 사이드바 **숨김**. 위→아래:

1. 상단 바: 좌 `IRIS` 타이틀 / 우 — IDE 토글 아이콘, 프로필, 설정, 최대화, 닫기  
2. 구체(Visualizer) 소형  
3. Live Activity (짧게)  
4. 채팅 (세로로 주 영역)  
5. 입력창  
6. 음성 파형  

일반 모드 복귀 시 기존 좌측 사이드바 + 와이드 레이아웃 복원.  
상태 칩(HERMES/MODEL 등)은 Companion에서 최소화하거나 상단 한 줄로만.

### IDE 아이콘 동작 (상태 머신)

| 현재 | 클릭 | 결과 |
|------|------|------|
| normal, IDE 없음 | IDE | IDE 실행(프로젝트 루트) → HWND 확보 → 타일 → companion |
| normal, IDE 있음 | IDE | 재실행 금지, 기존 HWND 타일만 → companion |
| companion | IDE | Iris normal 레이아웃만, IDE 창 유지(위치 강제 복귀 불필요) |
| companion → 다시 IDE | IDE | 기존 IDE 타일만 재적용, 재실행 금지 |

Iris 닫기 ≠ IDE 종료.

### Hermes

- Companion/normal 모두 `_use_hermes_backend()` 유지.
- 채팅 시 가능하면 메시지 또는 시스템 컨텍스트에 `Project root: {project_root}` 첨부.
- IDE 내장 AI와 통신하지 않음.

## Output (구현 범위)

최소 파일 후보 (필요 시에만, 과잉 추상화 금지):

1. `iris/system/ide_launcher.py` — 경로 해석, 실행, “이미 실행 중” 탐지(프로세스명 `Cursor.exe` / `Code.exe`)
2. `iris/system/ide_tiler.py` 또는 `window_controller` 확장 — work area 타일, hwnd 기준 `SetWindowPos`
3. `user_profile` + `user_profile_dialog` — IDE 선택/경로
4. `main_window.py` — 모드 전환, IDE 아이콘 콜백, companion 레이아웃 토글
5. (필요 시) companion용 얇은 헤더 위젯 — 기존 `DragTab` 재사용 가능하면 재사용

검증:

- 프로필에서 Cursor 선택 → IDE 아이콘 → Cursor 창이 왼쪽 ~80%, Iris 오른쪽 ~20%
- 재클릭 → Iris 일반 UI, Cursor는 그대로
- 다시 클릭 → 타일만, Cursor 프로세스 새로 안 뜸 (PID/HWND 유지)
- VS Code 미설치 시 명확한 오류, Cursor는 동작
- 채팅이 Hermes로 가는지 (HERMES Connected)

## 명시적 비범위

- Iris 창 안에 IDE HWND 임베드
- Cursor SDK / IDE AI 브릿지
- 풀 IDE UI(파일 트리·LSP)를 Iris에 구현
- Linux/macOS 완벽 지원 (스텁만 허용)

---

## Agent에게 한 줄로

프로필 기반 IDE(Cursor/VS Code) 선택 + 별도 창 80:20 타일 + Iris companion 슬림 UI 토글(재실행 금지)을 위 경로·제약을 지켜 구현해라.
