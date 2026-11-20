# Iris Agent skills (Iris Control Surface)

Iris가 떠 있을 때만 동작한다. 제품 채팅 경로는 **SpeakTools**(native). iris-control MCP는 제품에 없다(동기화 시 scrub; stdio tombstone `TOOLS=[]`).

저장소 소스: `integrations/iris-skills/iris-agent/`.  
에이전트 홈 설치(정본): `skills/iris-agent/`.  
한 릴리스 호환: 기존 `skills/iris-control/`은 sync 시 정본으로 복사·읽기 폴백한다.

## 자동 설치 (Iris 기동 시)

Iris 시작 시 `iris.system.iris_agent_control_sync`가:

1. 제품 기본: `mcp_servers.iris-control` **제거**/scrub (SpeakTools)
2. 같은 config에 `mcp_servers.mobile-mcp` upsert  
   (`npx -y @mobilenext/mobile-mcp@latest`, `ANDROID_HOME`/`ANDROID_SDK_ROOT`/`PATH`=Iris SDK)  
3. `skills/iris-agent/`에 `SKILL_NAMES` 전부 복사 (legacy `skills/iris-control/` 마이그레이션 후):  
   `iris-work-start`, `iris-work-end`, `iris-session-status`, `iris-vibe-code`, `iris-emulator`, `iris-mobile-mcp`, `iris-browser`, `iris-learning`, `iris-calendar`, `iris-wiki`, `iris-pdf`, `iris-past-chats`, `iris-email`
4. `memories/MEMORY.md`에 Iris control 힌트 append (1회)  
5. 설정이 바뀌었고 gateway가 이미 떠 있으면 `--replace` 재기동  

→ **Iris를 꺼도 에이전트 홈 디스크에 남음** (재시작 유지).

수동:

```powershell
py -3 -m iris.system.iris_agent_control_sync --apply
```

Iris Agent sync 상태: `%USERPROFILE%\.iris-light\hermes_iris_control_sync.json` (온디스크 파일명은 호환 유지)

## 도구

- SpeakTools (제품): `PHASE4_ALLOWLIST` grants만 직접 노출 (`ping`, `get_state`, `get_catalog`, `control.invoke`, `shell.run`, `project.run`, …). PDF: `content.extract`, `content.dump_lab_scripts`, `wiki.import_content`, `note.export_pdf` (+ 스킬 `iris-pdf`).
- 그 밖 Control 액션은 `control.invoke`로만 — 개수는 `get_catalog` / `action_catalog.json` 기준 (고정 숫자를 README에 박지 않음).
- `control.invoke` — `{action, args?}`로 등록된 Control 액션 실행 (기존 risk/confirm 게이트 유지)
- Shell: Iris Agent terminal 비활성. 제품은 `shell.run`(홈 Iris Shell), IDE는 `project.run`.
- mobile-mcp: `mobile_list_available_devices`, `mobile_take_screenshot`, `mobile_list_elements_on_screen`, `mobile_click_on_screen_at_coordinates`, … (스킬 `iris-mobile-mcp` 참고)

라우팅: 에뮬 기동/종료/AVD → `emulator.*` · UI 탐색·탭·입력 → mobile-mcp.

## 전제 (mobile-mcp)

- Node 20+ (`npx` PATH)
- Android SDK (Iris `android_emulator._sdk_root()`와 동일)
- 프로젝트 AVD `IrisLight_Pixel`

## 스모크 체크리스트 (mobile-mcp)

1. Iris 실행 → Settings MCP/스킬 동기화 (또는 위 `--apply`)
2. Iris Agent 새 채팅 (gateway reload 후)
3. `emulator.launch` → adb device (`emulator-*`)
4. Iris Agent에서 mobile-mcp tool list 확인 → `mobile_list_available_devices`
5. `mobile_take_screenshot` (옵션: 설정 앱 실행 후 BACK)

인스타 DM·저장함 자동화는 **미지원** (앱 열기 수준만 실험).

## 기타 스모크

```powershell
py -3 -m iris.system.control_surface
py -3 iris\ui\_check_ide_control_scenarios.py
py -3 -m iris.system.iris_agent_control_sync
```
