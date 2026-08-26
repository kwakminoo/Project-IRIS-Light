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

import time

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

# 명령을 보낸 뒤 상태 전환을 기다리는 시간. 전화 받기는 빨라야 하므로 짧게 잡고,
# 촘촘히 확인해서 되는 즉시 돌아온다.
_VERIFY_TIMEOUT_SEC = 1.8
_VERIFY_POLL_SEC = 0.2
# 벨이 막 울리기 시작한 순간에 보낸 키는 삼켜지는 일이 있다(실측 5회 중 2회).
# 같은 전략을 한 번 더 시도해 건진다.
_ATTEMPTS_PER_STRATEGY = 3

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


# `cmd telecom` 은 구현이 없어도 **종료 코드 0** 을 준다.
# 에뮬레이터 이미지(예: Android 33)에서는 accept-ringing-call/end-call 이
# 통째로 없는데도 rc=0 + "No shell command implementation." 만 나온다.
# 종료 코드만 보면 성공으로 착각해 폴백이 영영 안 걸린다.
_NOT_IMPLEMENTED = (
    "no shell command implementation",
    "unknown command",
    "unsupported command",
    "usage: telecom",
)


def _command_succeeded(code: int, out: str, err: str) -> bool:
    if code != 0:
        return False
    blob = f"{out or ''} {err or ''}".strip().lower()
    return not any(marker in blob for marker in _NOT_IMPLEMENTED)


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


def _wait_for_state(serial: str, wanted: tuple[CallState, ...], timeout: float) -> bool:
    """명령을 보낸 뒤 상태가 실제로 바뀌었는지 확인한다."""
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if read_call_state(serial).state in wanted:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_VERIFY_POLL_SEC)


def _apply_verified(
    serial: str,
    strategies: tuple[tuple[list[str], str], ...],
    wanted: tuple[CallState, ...],
    *,
    timeout: float = _VERIFY_TIMEOUT_SEC,
) -> tuple[bool, str]:
    """전략을 순서대로 시도하되, **상태가 실제로 바뀌어야** 성공으로 본다.

    종료 코드만 믿으면 안 된다. `cmd telecom` 은 구현이 없어도 rc=0 을 주고,
    `input keyevent KEYCODE_ENDCALL` 은 벨이 울리는 중에는 rc=0 을 주면서도
    아무 일도 하지 않는다. 되돌릴 수 없는 동작에서 "됐다"고 거짓 보고하면
    사용자는 전화를 놓친 줄도 모른다.
    """
    detail = ""
    for args, label in strategies:
        for attempt in range(_ATTEMPTS_PER_STRATEGY):
            try:
                code, out, err = adb_run(args, serial=serial, timeout=8.0)
            except AdbError as exc:
                detail = str(exc)
                break
            if not _command_succeeded(code, out, err):
                detail = (err or out or "").strip() or detail
                break  # 구현이 없는 명령은 다시 보내도 소용없다
            if _wait_for_state(serial, wanted, timeout):
                return True, label
            # 벨이 막 울리기 시작한 순간에는 키 입력이 삼켜진다. 한 번 더 보낸다.
            # 받기/끊기 키는 이미 그 상태면 아무 일도 하지 않으므로 재시도가 안전하다.
            detail = "명령은 통과했지만 통화 상태가 바뀌지 않았습니다."
    return False, detail


def answer_call(serial: str | None = None) -> tuple[bool, str]:
    """전화를 받는다. (성공, 메시지).

    `cmd telecom accept-ringing-call` 이 정공법이지만 API 26 미만이나 일부
    이미지에는 없다. 실패하면 헤드셋 훅 키로 폴백한다.
    """
    try:
        ser = serial or require_serial()
    except AdbError as exc:
        return False, str(exc)

    ok, detail = _apply_verified(
        ser,
        (
            (["shell", "cmd", "telecom", "accept-ringing-call"], "telecom"),
            # 헤드셋 훅 키. telecom 이 없는 에뮬레이터 이미지에서 실제로 되는 건 이쪽.
            (["shell", "input", "keyevent", "KEYCODE_CALL"], "keyevent"),
        ),
        (CallState.ACTIVE,),
    )
    if ok:
        return True, "전화를 받았습니다."
    return False, detail or "전화를 받지 못했습니다."


def end_call(serial: str | None = None) -> tuple[bool, str]:
    """통화를 끊거나 수신을 거절한다. 두 경우 모두 같은 명령이다."""
    try:
        ser = serial or require_serial()
    except AdbError as exc:
        return False, str(exc)

    ringing = read_call_state(ser).state is CallState.RINGING
    ok, detail = _apply_verified(
        ser,
        (
            (["shell", "cmd", "telecom", "end-call"], "telecom"),
            (["shell", "input", "keyevent", "KEYCODE_ENDCALL"], "keyevent"),
        ),
        (CallState.IDLE,),
    )
    if ok:
        return True, "통화를 종료했습니다."
    if ringing:
        # 벨이 울리는 중의 거절은 기기/이미지에 따라 간헐적으로 실패한다.
        # telecom 셸 명령이 없는 에뮬레이터 이미지에서 KEYCODE_ENDCALL 이
        # rc=0 을 주면서도 상태를 못 바꾸는 경우를 실제로 확인했다
        # (통화 중 종료는 같은 키로 항상 된다).
        # 실패를 성공이라 보고하면 사용자는 전화를 놓친 줄도 모르므로,
        # 되는 대안(벨소리 끄기)을 같이 알려 준다.
        return False, "수신 거절이 적용되지 않았습니다. 벨소리 끄기는 가능합니다."
    return False, detail or "통화를 종료하지 못했습니다."


def silence_ringer(serial: str | None = None) -> tuple[bool, str]:
    """벨소리만 끈다. 통화는 그대로 들어와 있다 — 되돌릴 수 있는 동작."""
    try:
        ser = serial or require_serial()
        code, out, err = adb_run(
            ["shell", "cmd", "telecom", "silence-ringer"], serial=ser, timeout=8.0
        )
        if _command_succeeded(code, out, err):
            return True, "벨소리를 껐습니다."
        # telecom 이 없는 이미지 폴백 — 볼륨 다운이 벨소리를 죽인다.
        # 통화는 그대로 들어와 있으므로 여전히 받을 수 있다.
        code, out2, err2 = adb_run(
            ["shell", "input", "keyevent", "KEYCODE_VOLUME_DOWN"], serial=ser, timeout=8.0
        )
        if _command_succeeded(code, out2, err2):
            return True, "벨소리를 껐습니다."
        return False, (err or err2 or out or "벨소리 끄기에 실패했습니다.").strip()
    except AdbError as exc:
        return False, str(exc)
