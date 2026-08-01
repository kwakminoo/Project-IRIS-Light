# Hermes ↔ Iris Control Surface

Iris가 떠 있을 때만 동작한다. Hermes가 Iris UI를 **tool-calling**으로 조작한다.

## 자동 설치 (Iris 기동 시)

Iris 시작 시 `iris.system.hermes_iris_control_sync`가:

1. `%LOCALAPPDATA%\hermes\config.yaml`에 `mcp_servers.iris-control` upsert  
2. 같은 config에 `mcp_servers.mobile-mcp` upsert  
   (`npx -y @mobilenext/mobile-mcp@latest`, `ANDROID_HOME`/`ANDROID_SDK_ROOT`/`PATH`=Iris SDK)  
3. `skills/iris-control/{iris-work-*,iris-vibe-code,iris-emulator,iris-mobile-mcp}` 복사  
4. `memories/MEMORY.md`에 Iris control 힌트 append (1회)  
5. 설정이 바뀌었고 gateway가 이미 떠 있으면 `--replace` 재기동  

→ **Iris를 꺼도 Hermes 디스크에 남음** (재시작 유지).

수동:

```powershell
py -3 -m iris.system.hermes_iris_control_sync --apply
```

상태: `%USERPROFILE%\.iris-light\hermes_iris_control_sync.json`

## 도구

- iris-control: `iris_get_state` / `iris_get_catalog` / `iris_invoke` (`emulator.*` 포함)
- mobile-mcp: `mobile_list_available_devices`, `mobile_take_screenshot`, `mobile_list_elements_on_screen`, `mobile_click_on_screen_at_coordinates`, … (스킬 `iris-mobile-mcp` 참고)

라우팅: 에뮬 기동/종료/AVD → `emulator.*` · UI 탐색·탭·입력 → mobile-mcp.

## 전제 (mobile-mcp)

- Node 20+ (`npx` PATH)
- Android SDK (Iris `android_emulator._sdk_root()`와 동일)
- 프로젝트 AVD `IrisLight_Pixel`

## 스모크 체크리스트 (mobile-mcp)

1. Iris 실행 → Settings MCP/스킬 동기화 (또는 위 `--apply`)
2. Hermes 새 채팅 (gateway reload 후)
3. `emulator.launch` → adb device (`emulator-*`)
4. Hermes에서 mobile-mcp tool list 확인 → `mobile_list_available_devices`
5. `mobile_take_screenshot` (옵션: 설정 앱 실행 후 BACK)

인스타 DM·저장함 자동화는 **미지원** (앱 열기 수준만 실험).

## 기타 스모크

```powershell
py -3 -m iris.system.control_surface
py -3 iris\ui\_check_ide_control_scenarios.py
py -3 -m iris.system.hermes_iris_control_sync
```
