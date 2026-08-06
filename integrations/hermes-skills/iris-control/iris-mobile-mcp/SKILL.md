---
name: iris-mobile-mcp
description: >
  Android 에뮬레이터·앱 UI를 Hermes mobile-mcp로 조작한다.
  Use when: 에뮬 앱 조작, 화면 탭, APK 설치 후 UI 조작, 모바일 MCP,
  스크린샷으로 버튼 눌러줘, 텍스트 입력해줘, Instagram 앱 열기(실험),
  mobile_list_available_devices, mobile_take_screenshot, mobile_click_on_screen.
  켜기/끄기/프로젝트 AVD 고정은 iris-emulator(iris-control emulator.*)를 쓰고,
  복잡한 UI 탐색·탭·입력은 이 스킬(mobile-mcp)을 쓴다.
---

# Iris + mobile-mcp (실험)

Windows + 로컬 Android SDK + 프로젝트 AVD `IrisLight_Pixel` 전제.
전제: Node 20+, `npx`, Hermes `mcp_servers.mobile-mcp` 등록
(`npx -y @mobilenext/mobile-mcp@latest`, Iris sync가 `ANDROID_HOME`/`PATH` 맞춤).

## Routing

| Intent | Where |
|--------|--------|
| 에뮬 켜기/끄기/상태, 프로젝트 AVD, Iris UI | `iris_invoke` → `emulator.*` / `workspace.open_mobile` (iris-emulator) |
| **Play 스토어 앱 설치** (인스타/텔레그램 등) | `iris_invoke` → `emulator.play_install` (iris-emulator) — 딥링크 + UI 트리라 더 안정적 |
| 화면 글자 확인·글자로 탭 | `iris_invoke` → `emulator.ui_texts` / `emulator.tap_text` (iris-emulator) |
| 디바이스 목록, 스크린샷, UI 요소, 좌표 탭/스와이프, APK 설치·실행·종료, 키 입력 | **mobile-mcp** tools below |

Do **not** reimplement mobile-mcp inside iris-control. Do **not** use iris-control alone for deep UI trees.

## mobile-mcp tools (canonical names)

Device: `mobile_list_available_devices`, `mobile_get_screen_size`, `mobile_get_orientation`, `mobile_set_orientation`  
Apps: `mobile_list_apps`, `mobile_launch_app`, `mobile_terminate_app`, `mobile_install_app`, `mobile_uninstall_app`  
Screen: `mobile_take_screenshot`, `mobile_save_screenshot`, `mobile_list_elements_on_screen`, `mobile_click_on_screen_at_coordinates`, `mobile_double_tap_on_screen`, `mobile_long_press_on_screen_at_coordinates`, `mobile_swipe_on_screen`, `mobile_start_screen_recording`, `mobile_stop_screen_recording`  
Input: `mobile_type_keys`, `mobile_press_button`, `mobile_open_url`  
Crashes: `mobile_list_crashes`, `mobile_get_crash`

## Steps

1. `iris_get_state` — `emulator_running` / `emulator_serial` / `emulator_avd`.
2. Not running → `iris_invoke` `emulator.launch` → poll `emulator.status` until serial (`emulator-*`) appears (boot can take tens of seconds; retry).
3. Then `mobile_list_available_devices` — prefer **IrisLight_Pixel** / serial matching Iris `emulator_serial` (usually `emulator-5554`). Multiple devices: ask or pick the Iris serial.
   If Iris `emulator_phase` is booting: `iris_invoke` `emulator.wait_ready` first.
4. UI work: `mobile_take_screenshot` and/or `mobile_list_elements_on_screen` → `mobile_click_on_screen_at_coordinates` / `mobile_type_keys` / `mobile_swipe_on_screen` / `mobile_press_button`.
5. APK: prefer `mobile_install_app` then `mobile_launch_app` (package name). Fallback: iris `emulator.install` / `emulator.start_app` if mobile-mcp unavailable.
   Play 스토어 설치는 mobile-mcp로 검색·좌표 탭을 시도하지 말고 `emulator.play_install`을 쓴다.
6. On failure: report serial, boot state, whether login/2FA is needed — do not invent success.

## Experimental examples (no guarantee)

- "설정 앱 열고 뒤로" → launch settings package → screenshot → `mobile_press_button` BACK.
- "인스타 열어줘" → `mobile_launch_app` / list apps for Instagram package if installed → simple open only.

## Do not

- Do **not** promise Instagram DM, saved posts, or multi-step social automation (unsupported / experimental only).
- Do **not** confuse with Iris companion / coding (`iris-vibe-code`).
- Do **not** try to change Iris UI state with mobile-mcp alone — use iris-control.
- Do **not** use dangerous/raw shell if any tool exposes it; stick to the tools listed above.
- iOS Simulator / mcp-baepsae: out of scope for this Iris Light Windows setup.
