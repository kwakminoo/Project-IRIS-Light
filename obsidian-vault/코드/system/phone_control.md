# phone_control

`iris/system/phone_control.py`

adb 기반 전화 상태 조회·통화 제어.

## 주요 정의

- `class CallState`
- `class CallSnapshot`
- `def _command_succeeded`
- `def _dumpsys`
- `def _parse_registry`
- `def _parse_telecom`
- `def read_call_state`
- `def read_caller_name`
- `def _wait_for_state`
- `def _apply_verified`
- `def answer_call`
- `def end_call`
- `def silence_ringer`

## 내부 의존성

- [[android_emulator]]
