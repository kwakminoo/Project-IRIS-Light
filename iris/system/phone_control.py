"""adb 기반 전화 상태 조회·통화 제어.

연결된 Android 기기(프로젝트 AVD)의 통화 상태를 읽고, 받기/거절/끊기를 보낸다.
Qt에 의존하지 않는 순수 함수 계층이다 — 폴링과 시그널은
`iris.monitoring.call_monitor` 가 담당한다.

상태 판정은 `dumpsys telephony.registry` 의 `mCallState` 를 본다.
  0 = IDLE, 1 = RINGING, 2 = OFFHOOK(통화 중)
기기/버전에 따라 이 값이 안 나오는 경우가 있어 `dumpsys telecom` 도 함께 본다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from iris.system.android_emulator import AdbError, adb_run, require_serial


class CallState(str, Enum):
    IDLE = "idle"
    RINGING = "ringing"
    ACTIVE = "active"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CallSnapshot:
    """한 시점의 통화 상태."""

    state: CallState = CallState.UNKNOWN
    number: str = ""
    caller: str = ""
    serial: str = ""
    error: str = ""

    @property
    def ringing(self) -> bool:
        return self.state is CallState.RINGING

    @property
    def display_name(self) -> str:
        """낭독·표시용 이름. 이름을 모르면 번호, 그것도 없으면 발신자 표기."""
        return self.caller or self.number or "알 수 없는 번호"


# mCallState=1 / mCallState = 1 둘 다 나온다
_CALL_STATE = re.compile(r"mCallState\s*=\s*(\d)")
_TELECOM_RINGING = re.compile(r"\b(RINGING|isRinging\s*[:=]\s*true)\b", re.IGNORECASE)
_TELECOM_ACTIVE = re.compile(r"\bACTIVE\b")
# dumpsys telephony.registry 의 발신번호 표기
_INCOMING_NUMBER = re.compile(r"mCallIncomingNumber\s*=\s*([+\d\-#*]{2,})")
# 전화 화면 UI 덤프에서 발신자 이름을 건질 때
_UI_TEXT = re.compile(r'text="([^"]{1,60})"')

_STATE_BY_CODE = {
    "0": CallState.IDLE,
    "1": CallState.RINGING,
    "2": CallState.ACTIVE,
}

# 전화 UI에서 이름이 아닌 게 뻔한 문구들 — 발신자 이름 후보에서 뺀다
_UI_NOISE = (
    "받기", "거절", "응답", "통화", "스피커", "음소거", "키패드", "메시지",
    "answer", "decline", "reject", "mute", "keypad", "speaker", "message",
    "수신전화", "발신전화", "incoming", "call", "휴대전화", "mobile",
)


def _dumpsys(service: str, serial: str, *, timeout: float = 6.0) -> str:
    code, out, _err = adb_run(["shell", "dumpsys", service], serial=serial, timeout=timeout)
    return out if code == 0 else ""


def _parse_registry(dump: str) -> tuple[CallState, str]:
    state = CallState.UNKNOWN
    match = _CALL_STATE.search(dump or "")
    if match:
        state = _STATE_BY_CODE.get(match.group(1), CallState.UNKNOWN)
    number = ""
    num_match = _INCOMING_NUMBER.search(dump or "")
    if num_match:
        number = num_match.group(1).strip()
    return state, number


def _parse_telecom(dump: str) -> CallState:
    body = dump or ""
    if not body:
        return CallState.UNKNOWN
    if _TELECOM_RINGING.search(body):
        return CallState.RINGING
    if _TELECOM_ACTIVE.search(body):
        return CallState.ACTIVE
    return CallState.UNKNOWN


def read_call_state(serial: str | None = None) -> CallSnapshot:
    """지금 통화 상태. adb 문제는 예외 대신 error 필드로 돌려준다.

    이 함수는 폴링 루프에서 초당 여러 번 불릴 수 있으므로 절대 던지지 않는다.
    """
    try:
        ser = serial or require_serial()
    except AdbError as exc:
        return CallSnapshot(state=CallState.UNKNOWN, error=str(exc))

    try:
        registry = _dumpsys("telephony.registry", ser)
        state, number = _parse_registry(registry)
        if state is CallState.UNKNOWN:
            state = _parse_telecom(_dumpsys("telecom", ser))
    except AdbError as exc:
        return CallSnapshot(state=CallState.UNKNOWN, serial=ser, error=str(exc))

    return CallSnapshot(state=state, number=number, serial=ser)


def read_caller_name(serial: str | None = None) -> str:
    """전화 화면에서 발신자 이름을 건진다. 실패하면 빈 문자열.

    UI 덤프는 느리다(수백 ms). 상태 폴링과 분리해서, 벨이 울리기 시작한
    그 순간에만 한 번 부른다.
    """
    try:
        ser = serial or require_serial()
        code, out, _err = adb_run(
            ["shell", "uiautomator", "dump", "/dev/tty"], serial=ser, timeout=8.0
        )
    except AdbError:
        return ""
    if code != 0 or not out:
        return ""
    for candidate in _UI_TEXT.findall(out):
        text = candidate.strip()
        if not text or len(text) > 30:
            continue
        low = text.lower()
        if any(noise in low for noise in _UI_NOISE):
            continue
        if text.replace("+", "").replace("-", "").isdigit():
            continue  # 번호는 registry 쪽에서 이미 읽는다
        return text
    return ""


def answer_call(serial: str | None = None) -> tuple[bool, str]:
    """전화를 받는다. (성공, 메시지).

    `cmd telecom accept-ringing-call` 이 정공법이지만 API 26 미만이나 일부
    이미지에는 없다. 실패하면 헤드셋 훅 키로 폴백한다.
    """
    try:
        ser = serial or require_serial()
    except AdbError as exc:
        return False, str(exc)

    try:
        code, _out, err = adb_run(
            ["shell", "cmd", "telecom", "accept-ringing-call"], serial=ser, timeout=8.0
        )
        if code == 0:
            return True, "전화를 받았습니다."
        code, _out, err2 = adb_run(
            ["shell", "input", "keyevent", "KEYCODE_CALL"], serial=ser, timeout=8.0
        )
        if code == 0:
            return True, "전화를 받았습니다."
        return False, (err or err2 or "전화 받기에 실패했습니다.").strip()
    except AdbError as exc:
        return False, str(exc)


def end_call(serial: str | None = None) -> tuple[bool, str]:
    """통화를 끊거나 수신을 거절한다. 두 경우 모두 같은 명령이다."""
    try:
        ser = serial or require_serial()
    except AdbError as exc:
        return False, str(exc)

    try:
        code, _out, err = adb_run(
            ["shell", "cmd", "telecom", "end-call"], serial=ser, timeout=8.0
        )
        if code == 0:
            return True, "통화를 종료했습니다."
        code, _out, err2 = adb_run(
            ["shell", "input", "keyevent", "KEYCODE_ENDCALL"], serial=ser, timeout=8.0
        )
        if code == 0:
            return True, "통화를 종료했습니다."
        return False, (err or err2 or "통화 종료에 실패했습니다.").strip()
    except AdbError as exc:
        return False, str(exc)


def silence_ringer(serial: str | None = None) -> tuple[bool, str]:
    """벨소리만 끈다. 통화는 그대로 들어와 있다 — 되돌릴 수 있는 동작."""
    try:
        ser = serial or require_serial()
        code, _out, err = adb_run(
            ["shell", "cmd", "telecom", "silence-ringer"], serial=ser, timeout=8.0
        )
        if code == 0:
            return True, "벨소리를 껐습니다."
        return False, (err or "벨소리 끄기에 실패했습니다.").strip()
    except AdbError as exc:
        return False, str(exc)
