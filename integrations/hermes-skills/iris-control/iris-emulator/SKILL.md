---
name: iris-emulator
description: >
  Control the Iris Light Android emulator (IrisLight_Pixel) via Iris Control Surface.
  Use when: 에뮬 켜줘, 에뮬 꺼줘, 에뮬 상태, APK 설치, Play 스토어에서 앱 설치,
  인스타그램/텔레그램 설치해줘, 설정 앱 열어, 패키지 실행,
  홈/뒤로, 좌표 탭, 화면 글자 눌러줘, 텍스트 입력, 스와이프, 스크린샷, logcat 보여줘,
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
| Play 스토어 앱 설치 | `emulator.play_install` | `{app: "instagram"}` or `{app: "org.telegram.messenger", timeout_s?: 300}` |
| APK 설치 | `emulator.install` | `{apk: "C:/path/app.apk"}` |
| 설정 앱 / 패키지 실행 | `emulator.start_app` | `{package: "com.android.settings"}` or `{package, activity?}` |
| 홈 / 뒤로 / 엔터 | `emulator.key` | `{key: "HOME"\|"BACK"\|"ENTER"\|"APP_SWITCH"\|"POWER"}` |
| 텍스트 입력 (영문) | `emulator.input_text` | `{text: "..."}` |
| 화면 글자 목록 | `emulator.ui_texts` | `{}` |
| 화면 글자 탭 | `emulator.tap_text` | `{text: "Install", exact?: false}` |
| 좌표 탭 | `emulator.tap` | `{x: int, y: int}` |
| 스와이프 | `emulator.swipe` | `{x1,y1,x2,y2, duration_ms?: 300}` |
| 스크린샷 | `emulator.screenshot` | `{path?: optional}` |
| logcat | `emulator.logcat_tail` | `{lines?: 100, filter?: "Tag:I"}` |

5. Confirm with `emulator.status` or returned `data` (screenshot `path`, install `output`).
   Launch 실패 시 `launch_log` 경로·로그 tail을 사용자에게 보고.

## Convenience

- "설정 앱 열어줘" → `emulator.start_app` with `package=com.android.settings` (or `package=settings` — Iris maps it).
- "인스타그램 설치해줘" → `emulator.play_install` `{app: "instagram"}`.
  별칭: instagram/인스타(그램), telegram/텔레그램, kakaotalk/카카오톡/카톡, youtube/유튜브,
  whatsapp, discord, facebook, twitter/x, line/라인, tiktok/틱톡, netflix, spotify, chrome.
  별칭에 없으면 패키지명(`com.example.app`)을 그대로 넘긴다.

## Notes

- `phase=booting` 이고 serial 없으면 install/screenshot 하지 말고 `wait_ready` 먼저.
- 한글 입력: `emulator.input_text`는 ASCII만. 한글은 에뮬 화면 IME (상태의 `keyboard_hint`).
- 좌표를 추측하지 말 것. `emulator.play_install`은 `market://` 딥링크로 상세 페이지에
  바로 들어간 뒤 UI 트리에서 설치 버튼 좌표를 계산한다. 다른 화면도 `emulator.ui_texts`
  → `emulator.tap_text` 순서를 쓰고, `emulator.tap`은 최후 수단.
- `play_install`이 "Google 계정 로그인이 필요합니다"로 실패하면 사용자에게 에뮬에서
  로그인하라고 안내한다. 임의로 계정 생성 플로우를 진행하지 말 것.

## Do not

- Do not run arbitrary `adb shell …` strings.
- Do not promise Instagram DM, saved posts, or multi-step in-app automation.
- Do not invent APK paths — ask the user for a real `.apk` path.
- Do not guess tap coordinates from a screenshot — use `emulator.tap_text`.
- If action fails with "에뮬레이터 미실행", launch + wait_ready then retry.
