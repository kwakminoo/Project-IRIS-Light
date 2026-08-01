---
name: iris-emulator
description: >
  Control the Iris Light Android emulator (IrisLight_Pixel) via Iris Control Surface.
  Use when: 에뮬 켜줘, 에뮬 꺼줘, 에뮬 상태, APK 설치, 설정 앱 열어, 패키지 실행,
  홈/뒤로, 좌표 탭, 텍스트 입력, 스와이프, 스크린샷, logcat 보여줘,
  Android emulator launch/kill/install/tap/input/screenshot/logcat.
  Do NOT use for Instagram DM or deep in-app flows — only basic adb actions.
  For UI tree / screenshot-driven taps and app flows, prefer iris-mobile-mcp (mobile-mcp).
---

# Iris emulator (phase 1)

Lifecycle (launch/kill/status) and project AVD stay here. Rich UI automation → **iris-mobile-mcp**.

## Steps

1. `iris_get_state` — check `emulator_running`, `emulator_phase`, `emulator_serial`,
   `emulator_adb_ready`, `emulator_boot_completed`, `emulator_avd`.
2. If not running: `iris_invoke` → `emulator.launch`
3. Then `emulator.wait_ready` (`{timeout_s?: 180}`) until `phase=ready` / boot_completed.
   Or poll `emulator.status` (`phase`: starting|booting|ready|stopped).
4. Pick action:

| User intent | Action | Args |
|-------------|--------|------|
| 상태 | `emulator.status` | `{}` |
| 켜줘 | `emulator.launch` | `{headless?: false}` |
| 부팅 대기 | `emulator.wait_ready` | `{timeout_s?: 180}` |
| 꺼줘 | `emulator.kill` | `{}` |
| APK 설치 | `emulator.install` | `{apk: "C:/path/app.apk"}` |
| 설정 앱 / 패키지 실행 | `emulator.start_app` | `{package: "com.android.settings"}` or `{package, activity?}` |
| 홈 / 뒤로 / 엔터 | `emulator.key` | `{key: "HOME"\|"BACK"\|"ENTER"\|"APP_SWITCH"\|"POWER"}` |
| 텍스트 입력 (영문) | `emulator.input_text` | `{text: "..."}` |
| 탭 | `emulator.tap` | `{x: int, y: int}` |
| 스와이프 | `emulator.swipe` | `{x1,y1,x2,y2, duration_ms?: 300}` |
| 스크린샷 | `emulator.screenshot` | `{path?: optional}` |
| logcat | `emulator.logcat_tail` | `{lines?: 100, filter?: "Tag:I"}` |

5. Confirm with `emulator.status` or returned `data` (screenshot `path`, install `output`).
   Launch 실패 시 `launch_log` 경로·로그 tail을 사용자에게 보고.

## Convenience

- "설정 앱 열어줘" → `emulator.start_app` with `package=com.android.settings` (or `package=settings` — Iris maps it).

## Notes

- `phase=booting` 이고 serial 없으면 install/screenshot 하지 말고 `wait_ready` 먼저.
- 한글 입력: `emulator.input_text`는 ASCII만. 한글은 에뮬 화면 IME (상태의 `keyboard_hint`).

## Do not

- Do not run arbitrary `adb shell …` strings.
- Do not promise Instagram DM, saved posts, or multi-step in-app automation.
- Do not invent APK paths — ask the user for a real `.apk` path.
- If action fails with "에뮬레이터 미실행", launch + wait_ready then retry.
