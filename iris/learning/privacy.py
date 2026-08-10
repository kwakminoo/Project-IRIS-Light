"""민감 입력 redact — password 컨트롤·로그인 창 + UIA IsPassword."""

from __future__ import annotations

import re

_SENSITIVE_TITLE = re.compile(
    r"(password|passwd|로그인|login|sign\s*in|credential|인증|otp|2fa)",
    re.I,
)
_PASSWORD_KEY_HINTS = frozenset({"password", "passwd", "pwd", "secret", "token"})


def looks_like_credential_window(window_title: str, process_name: str = "") -> bool:
    blob = f"{window_title} {process_name}"
    return bool(_SENSITIVE_TITLE.search(blob))


def is_password_control_os() -> bool:
    """Windows: UIA IsPassword → EM_GETPASSWORDCHAR → ES_PASSWORD."""
    try:
        if _uia_focused_is_password():
            return True
    except Exception:
        pass
    try:
        if _edit_password_char():
            return True
    except Exception:
        pass
    try:
        return _es_password_style()
    except Exception:
        return False


def _uia_focused_is_password() -> bool:
    """UI Automation IsPassword (A). comtypes 선택적."""
    import sys

    if sys.platform != "win32":
        return False
    try:
        import comtypes
        import comtypes.client
    except ImportError:
        return False

    # IUIAutomation CLSID
    uia = comtypes.client.CreateObject(
        "{ff48dba4-60ef-4201-aa87-54103ed9648d}",
    )
    # GetFocusedElement
    get_focus = getattr(uia, "GetFocusedElement", None)
    if get_focus is None:
        return False
    el = get_focus()
    if el is None:
        return False
    # UIA_IsPasswordPropertyId = 30019
    try:
        val = el.GetCurrentPropertyValue(30019)
        return bool(val)
    except Exception:
        # CurrentIsPassword on some wrappers
        return bool(getattr(el, "CurrentIsPassword", False))


def _edit_password_char() -> bool:
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetFocus()
    if not hwnd:
        return False
    # EM_GETPASSWORDCHAR = 0x00D2
    ch = user32.SendMessageW(hwnd, 0x00D2, 0, 0)
    return int(ch) != 0


def _es_password_style() -> bool:
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetFocus()
    if not hwnd:
        return False
    style = user32.GetWindowLongW(hwnd, -16)
    return bool(style & 0x0020)  # ES_PASSWORD


def redact_text_if_needed(
    text: str | None,
    *,
    window_title: str = "",
    process_name: str = "",
    is_password_control: bool = False,
) -> str | None:
    if text is None:
        return None
    if is_password_control or looks_like_credential_window(window_title, process_name):
        return "[REDACTED]"
    return text


def redact_key_if_needed(
    key: str | None,
    *,
    window_title: str = "",
    process_name: str = "",
    is_password_control: bool = False,
) -> str | None:
    if key is None:
        return None
    if is_password_control or looks_like_credential_window(window_title, process_name):
        if len(key) == 1 or key.lower() in _PASSWORD_KEY_HINTS:
            return "[REDACTED]"
    return key
