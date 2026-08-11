"""입력 훅 자가진단 + Win32 폴백 힌트."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger("iris.learning.hook_probe")


@dataclass
class HookProbeResult:
    ok: bool
    mouse_ok: bool = False
    keyboard_ok: bool = False
    backend: str = ""  # pynput | win32 | none
    messages: list[str] = field(default_factory=list)
    security_hint: str = ""
    accessibility_hint: str = ""
    elevation_hint: str = ""


def _probe_win32(result: HookProbeResult) -> HookProbeResult:
    from iris.learning.permission import is_process_elevated

    try:
        import ctypes

        user32 = ctypes.windll.user32
        if hasattr(user32, "SetWindowsHookExW"):
            result.backend = "win32"
            result.mouse_ok = True
            result.keyboard_ok = True
            result.ok = True
            result.messages.append("Win32 low-level hook API 사용 가능 (폴백)")
            result.messages.append(
                "별도 프로그램 연결 불필요 — 학습 시작 시 recorder가 자동으로 Win32 훅을 사용합니다."
            )
            if not is_process_elevated():
                result.messages.append(result.elevation_hint)
            return result
        result.messages.append("Win32 SetWindowsHookExW 없음")
    except Exception as exc:
        result.messages.append(f"Win32 hook 불가: {exc}")
    result.backend = "none"
    result.ok = False
    return result


def probe_input_hooks(*, timeout_sec: float = 1.2) -> HookProbeResult:
    """짧은 리스너 기동으로 훅 가능 여부 확인."""
    from iris.learning.permission import request_elevation_hint

    result = HookProbeResult(ok=False)
    result.elevation_hint = request_elevation_hint()
    result.security_hint = (
        "백신/EDR가 키보드·마우스 후킹을 차단할 수 있습니다. "
        "Windows 보안 또는 보안 제품에서 Iris/python 예외를 허용하세요."
    )
    result.accessibility_hint = (
        "일부 환경에서는 ‘앱이 다른 앱을 제어’ 관련 정책이 필요합니다. "
        "회사 PC면 IT 정책·그룹정책을 확인하세요."
    )

    # 1) pynput
    try:
        from pynput import keyboard, mouse

        mouse_ok = {"v": False}
        key_ok = {"v": False}

        def on_move(x, y):
            mouse_ok["v"] = True

        def on_press(key):
            key_ok["v"] = True

        ml = mouse.Listener(on_move=on_move)
        kl = keyboard.Listener(on_press=on_press)
        ml.start()
        kl.start()
        time.sleep(min(0.35, timeout_sec))
        mouse_ok["v"] = mouse_ok["v"] or ml.running
        key_ok["v"] = key_ok["v"] or kl.running
        try:
            ml.stop()
            kl.stop()
        except Exception:
            pass
        result.mouse_ok = bool(mouse_ok["v"])
        result.keyboard_ok = bool(key_ok["v"])
        if result.mouse_ok and result.keyboard_ok:
            result.ok = True
            result.backend = "pynput"
            result.messages.append("pynput 훅 사용 가능")
            return result
        result.messages.append("pynput 리스너 부분 실패 — Win32 폴백 검사")
    except ImportError as exc:
        result.messages.append(f"pynput 사용 불가: {exc}")
        result.messages.append(
            "해결: 설정에서 ‘pynput 설치’를 누르거나, Iris가 쓰는 Python에 "
            "`python -m pip install pynput` 실행"
        )
    except Exception as exc:
        result.messages.append(f"pynput 오류: {exc}")

    return _probe_win32(result)


class Win32FallbackNote:
    """실제 LL hook 구현은 recorder가 pynput 실패 시 시도."""

    pass
