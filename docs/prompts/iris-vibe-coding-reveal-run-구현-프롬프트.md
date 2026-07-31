# 구현 프롬프트: Iris Vibe-Coding Reveal + Run (A/B + IDE 터미널 본문 / 채팅 요약)

> 이 문서를 Agent에게 그대로 넘기면 된다.  
> Ask/설계 대화(2026-07-28) 합의안 기준.  
> 선행: IDE Companion Mode + Iris Control Surface (`ide.enter_companion`, `ide.open_folder`, `project.write_file` 등).

---

## Context

- 프로젝트: Project-IRIS-Light (PyQt6 HUD)
- 바이브코딩 AI: **항상 Iris → Hermes → Ollama**. IDE 내장 AI(Cursor Composer 등) 대체/제어 **금지**.
- IDE는 **별도 창** Companion 타일(약 80:20). HWND 임베드 금지.
- 제어 경로: Control Surface HTTP + MCP `iris_get_state` / `iris_get_catalog` / `iris_invoke`
  - 바인딩: `iris/ui/control_bindings.py`
  - 런처: `iris/system/ide_launcher.py` (`resolve_ide_cli`, `open_folder_in_ide`, `-g` 후보)
  - 파일 쓰기: `iris/system/project_ops.write_project_file` — **디스크만** 쓰고 IDE 탭을 열지 않음 (현재 갭)
  - 스킬: `integrations/hermes-skills/iris-control/*` + `hermes_iris_control_sync` / `hermes_memory_nudge`
- 사용자 테스트 결과: 폴더 열기·파일 생성·쓰기는 되나, **생성 직후 가운데 에디터에 파일이 안 뜸**. 실행은 IDE를 “조작”하는 느낌이 없고, 결과는 **IDE 터미널 본문 + Iris 채팅 요약**이 바람직함.

### 설계 합의 (유지)

| 채널 | 역할 |
|------|------|
| IDE 화면 | 무대 — 열린 파일, (가능하면) 통합 터미널에 실행 로그 전문 |
| Iris 채팅 | 지휘 + 진행 설명 + **실행 결과 요약** (전문 dump 금지) |
| 디스크 | 진실의 원천 (`project.write_file`) |

- Cursor/VS Code **전용 MCP 서버를 새로 붙이지 말 것**. 기존 `iris-control` MCP만 확장.
- UI 자동화(키 입력으로 타이핑 흉내) **금지** (YAGNI·깨짐).
- ponytail: 최소 코드. 의도적 단순화는 `ponytail:` 주석.

---

## Goal

1. **레벨 A (필수):** 파일 생성/쓰기 후 IDE에서 해당 파일을 **열어 가운데 에디터에 보이게** 한다.
2. **레벨 B (필수):** 파일이 열린 뒤 **청크 단위로 내용이 늘어나** 사용자가 “작성되는 것”을 볼 수 있게 한다.
3. **실행:** 사용자 “실행해줘” 시
   - **본문(stdout/stderr 전문)** 은 가능하면 **IDE 통합 터미널**에 보이게 한다.
   - Iris 채팅에는 **요약만** (exit code, 성공/실패, 핵심 몇 줄/에러 헤드).
4. Hermes가 순서를 지키도록 **스킬 + MEMORY nudge** 보강.
5. 기존 Companion/타일/재실행 금지/이모지 필터/Hermes 채팅 경로를 깨지 말 것.

---

## Constraints

- Windows 우선. Cursor / VS Code CLI 우선 (`ide_launcher.resolve_ide_cli`).
- 새 의존성 최소화. pywinauto/전역 키후킹 금지.
- `project.write_file`의 path escape (`..` 금지, project_root 밖 금지) 유지·동일 규칙 적용.
- 채팅에 실행 로그 전문을 붙이지 말 것 (길이 truncate; 전문은 IDE 터미널 또는 `.iris/last_run.log`).
- IDE 내장 AI / Cursor SDK / 임베드 금지.
- 실패 시 Live Activity에 짧은 텍스트만 (이모지 없음).

---

## UX (사용자가 체감해야 하는 시나리오)

### S1 — 파일 만들고 보이기 (A)

1. 채팅: “구구단 파일 만들어줘”
2. Hermes → `project.write_file` (또는 scaffold) with **open/reveal**
3. IDE 가운데에 `gugudan.py`(등) 탭이 선택·표시됨
4. 채팅: 짧은 확인 (“`gugudan.py` 열었어요”)

### S2 — 작성되는 느낌 (B)

1. 파일이 이미 열린 상태(또는 첫 청크 쓰기 직후 open)
2. 내용을 **청크**로 여러 번 write (간격 두어 IDE 파일 감시로 에디터가 갱신)
3. 사용자는 IDE에서 코드가 늘어나는 것을 봄
4. 채팅에는 “작성 중 / 완료” 정도만 (전체 코드를 채팅에 반복 dump하지 말 것 — 필요 시 한 번 요약)

### S3 — 실행

1. 채팅: “실행해줘”
2. Hermes → `project.run` (또는 동등 액션)
3. **IDE 통합 터미널**에 명령 + 출력 전문이 보임 (Primary)
4. Iris 채팅에는 예: `exit 0 · 9줄 출력 · 마지막: 9×9=81` 수준의 **요약**
5. IDE 터미널 주입이 실패하면 Fallback — 채팅에 “터미널 대신 로그 파일을 열었습니다” 한 줄 + 요약

---

## Interface / 액션 설계

### 1) `ide.open_file` (신규)

```text
args:
  path?: absolute file path
  project_root?: str   # 없으면 프로필 project_root
  rel_path?: str       # path 없을 때
  line?: int = 1
  column?: int = 1
  reuse_window?: bool = true
returns:
  ok, { path, cli_used?, error? }
```

동작:

- Cursor/VS Code: `cli [--reuse-window] -g path:line[:column]`
- CLI 없거나 JetBrains 등 미지원이면: exe에 파일 경로 전달 등 **최선의 폴백**, 불가 시 명확한 error.

### 2) `project.write_file` 확장

```text
기존: project_root, rel_path, content
추가:
  open?: bool = true          # A: 쓰기 후 ide.open_file
  stream?: bool = false       # B: 청크 스트리밍 쓰기
  chunk_chars?: int = 80
  chunk_delay_ms?: int = 120
```

### 3) `project.run` (신규)

```text
합의된 기본 동작:
  1) Cursor/VS Code이면 tasks.json upsert 후 통합 터미널 실행 시도
  2) 실패 시 Iris subprocess 1회 → last_run.log → ide.open_file(log)
  3) 채팅: summary + exit_code + tail만. 전문 금지.
  이중 실행 금지.
```

### 4) Skills / MEMORY

- 신규 `iris-vibe-code` 스킬
- `iris-work-start` 소폭 보강
- `hermes_memory_nudge` 버전 bump

---

## 명시적 비범위

- Cursor/VS Code MCP 서버 신규 연동
- IDE 확장(Extension) 개발
- pywinauto / 실제 키보드 타이핑 연출
- Monaco/Theia를 Iris 안에 임베드
- JetBrains 완벽 터미널 주입 (폴백 로그만으로 허용)
- 채팅 아티팩트에 전체 실행 로그 스트리밍

---

## Agent에게 한 줄로

`ide.open_file` + `write_file(open/stream)`으로 A/B reveal을 넣고, `project.run`으로 실행 본문은 IDE 터미널(실패 시 `.iris` 로그)에·요약만 Iris 채팅에 보이게 하며, Hermes 스킬/nudge로 바이브코딩 순서를 고정해라. Cursor 전용 MCP·UI 자동화는 하지 마라.
