"""녹화 중 '무엇을 입력했는지'를 글자 그대로 되살린다.

저수준 훅은 IME 이전의 가상 키(VK)만 본다. 한글 모드에서 "안녕"을 치면 D K S S U D
가 들어오고, Shift 정보도 키 이름만으로는 사라진다. 그래서 키를 모아 두었다가
입력이 끝나는 순간(Enter·Tab·클릭·창 전환·단축키) 한 번에 정리한다.

1순위: 그 순간 포커스된 입력창의 글자를 WM_GETTEXT 로 직접 읽는다 (카톡 입력창
       같은 RichEdit 는 다른 프로세스여도 읽힌다). Enter 는 앱이 처리하기 전에 훅이
       먼저 보므로, 보내기 직전의 글자를 읽을 수 있다.
2순위: 읽지 못하면 키 순서를 두벌식으로 조합한 글자(hangul.compose).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from iris.learning.hangul import compose

VK_BACK, VK_TAB, VK_RETURN, VK_ESCAPE, VK_SPACE = 0x08, 0x09, 0x0D, 0x1B, 0x20
VK_HANGUL = 0x15
VK_RMENU = 0xA5  # 노트북 자판은 오른쪽 Alt 가 한/영 키
TOGGLE = "\x00"  # TypingBuffer.keys 안에서 한/영 전환 자리
_SHIFT = {0x10, 0xA0, 0xA1}
_CTRL = {0x11, 0xA2, 0xA3}
_ALT = {0x12, 0xA4, 0xA5}
_WIN = {0x5B, 0x5C}
MODIFIER_VKS = _SHIFT | _CTRL | _ALT | _WIN

_SHIFT_DIGITS = ")!@#$%^&*("
_OEM = {
    0xBA: (";", ":"), 0xBB: ("=", "+"), 0xBC: (",", "<"), 0xBD: ("-", "_"),
    0xBE: (".", ">"), 0xBF: ("/", "?"), 0xC0: ("`", "~"), 0xDB: ("[", "{"),
    0xDC: ("\\", "|"), 0xDD: ("]", "}"), 0xDE: ("'", '"'),
}
_NUMPAD = {0x6A: "*", 0x6B: "+", 0x6D: "-", 0x6E: ".", 0x6F: "/"}
_KEY_NAMES = {
    VK_RETURN: "enter", VK_TAB: "tab", VK_ESCAPE: "esc", VK_BACK: "backspace",
    VK_SPACE: "space", 0x2E: "delete", 0x24: "home", 0x23: "end", 0x21: "pageup",
    0x22: "pagedown", 0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down",
}


def vk_to_char(vk: int, shift: bool) -> str | None:
    """글자를 만드는 키면 그 글자 (영문 자판 기준), 아니면 None."""
    if 0x41 <= vk <= 0x5A:
        c = chr(vk)
        return c if shift else c.lower()
    if 0x30 <= vk <= 0x39:
        return _SHIFT_DIGITS[vk - 0x30] if shift else chr(vk)
    if 0x60 <= vk <= 0x69:
        return chr(ord("0") + vk - 0x60)
    if vk == VK_SPACE:
        return " "
    if vk in _OEM:
        return _OEM[vk][1 if shift else 0]
    return _NUMPAD.get(vk)


def vk_key_name(vk: int) -> str:
    if vk in _KEY_NAMES:
        return _KEY_NAMES[vk]
    if 0x70 <= vk <= 0x87:
        return f"f{vk - 0x6F}"
    c = vk_to_char(vk, False)
    if c and c != " ":
        return c
    return f"vk{vk:02x}"


def is_text_field_class(class_name: str) -> bool:
    """WM_GETTEXT 결과가 '입력한 글자'인 창인지. 목록·버튼은 자기 이름을 돌려준다
    (카톡 친구 목록이 'ContactListCtrl_0x…'를 돌려준 실제 사례)."""
    c = (class_name or "").lower()
    return "edit" in c or c.startswith("richedit")


def looks_hangul(composed: str) -> bool:
    """두벌식으로 조합한 결과가 한글 문장 같은지.

    한글로 친 글자는 거의 다 완성된 글자가 되고, 영어 단어는 홀로 남는 자모가 섞인다
    ('hello world' → 'ㅗ디ㅣㅐ 재깅'). 완성 글자가 홀로 남은 자모의 두 배 이상이면 한글."""
    syllables = sum(1 for c in composed if "가" <= c <= "힣")
    stray = sum(1 for c in composed if "ㄱ" <= c <= "ㅣ")
    return syllables >= 1 and syllables >= 2 * stray


@dataclass
class TypedText:
    text: str
    raw_keys: str
    source: str  # control | hangul | latin
    focus_class: str = ""
    # 입력이 끝난 순간 입력창 전체 글자 (앞서 쳐 둔 글자 포함) — 보낸 메시지 그 자체
    field_text: str = ""


@dataclass
class TypingBuffer:
    """한 번의 연속 입력. flush 하면 TypedText 가 나온다."""

    keys: list[str] = field(default_factory=list)  # TOGGLE 은 한/영 키를 누른 자리
    hangul: bool = False  # 입력을 시작할 때 IME 가 알려 준 모드 (카톡 등은 늘 False)
    focus_hwnd: int = 0
    started: bool = False

    def add(self, ch: str) -> None:
        self.keys.append(ch)

    def backspace(self) -> None:
        # 두벌식에서 백스페이스는 자모 하나를 지운다 — 키 하나를 지우면 같다
        for i in range(len(self.keys) - 1, -1, -1):
            if self.keys[i] != TOGGLE:
                del self.keys[i]
                return

    def toggle_hangul(self) -> None:
        self.keys.append(TOGGLE)

    def reset(self) -> None:
        self.keys = []
        self.focus_hwnd = 0
        self.started = False

    def raw(self) -> str:
        return "".join("[한/영]" if k == TOGGLE else k for k in self.keys)

    def _mixed(self) -> str:
        """한/영 키로 나뉜 구간마다 한글·영문을 정해 붙인다.

        처음 모드를 IME 가 정확히 알려 주지 않으므로 '영문으로 시작'과 '한글로 시작'
        두 경우를 다 맞춰 보고, 구간 글자가 그 모드다운 쪽을 고른다."""
        segs = "".join(self.keys).split(TOGGLE)
        if len(segs) == 1:
            seg = segs[0]
            return compose(seg) if (self.hangul or looks_hangul(compose(seg))) else seg

        def build(start_hangul: bool) -> tuple[int, str]:
            score, out = 0, []
            for n, seg in enumerate(segs):
                mode = start_hangul if n % 2 == 0 else not start_hangul
                fits = looks_hangul(compose(seg)) == mode
                score += len(seg) if fits else 0
                out.append(compose(seg) if mode else seg)
            return score, "".join(out)

        a, b = build(False), build(True)
        if a[0] == b[0]:
            return b[1] if self.hangul else a[1]
        return a[1] if a[0] > b[0] else b[1]

    def resolve(self, control_text: str | None, focus_class: str = "") -> TypedText | None:
        raw = "".join(k for k in self.keys if k != TOGGLE)
        if not raw.strip() and not (control_text or "").strip():
            return None
        latin = raw
        hangul = compose(raw)
        guess = self._mixed()
        read = (control_text or "").strip() if is_text_field_class(focus_class) else ""
        if read and len(read) <= 2000:
            for cand, src in ((guess, "keys"), (hangul, "hangul"), (latin, "latin")):
                if cand.strip() and cand.strip() in read:
                    return TypedText(cand.strip(), raw, src, focus_class, read)
            # 친 글자가 입력창 글자에 없다 — 카톡 입력창은 비어 있을 때 안내 문구 "메시지 입력"을
            # 글자로 돌려준다 (실제 사례). 이때는 키로 조합한 글자를 믿는다.
        if not guess.strip():
            return None
        return TypedText(guess.strip(), raw, "keys", focus_class)


# ----------------------------------------------------------------------
# Win32 — 포커스 창 글자 읽기, IME 한/영 상태
# ----------------------------------------------------------------------

def focused_control(foreground_hwnd: int) -> int:
    if sys.platform != "win32" or not foreground_hwnd:
        return 0
    try:
        import ctypes
        from ctypes import wintypes

        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                ("rcCaret", wintypes.RECT),
            ]

        user32 = ctypes.windll.user32
        tid = user32.GetWindowThreadProcessId(wintypes.HWND(foreground_hwnd), None)
        info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        if not user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
            return 0
        return int(info.hwndFocus or 0)
    except Exception:
        return 0


def control_class(hwnd: int) -> str:
    if sys.platform != "win32" or not hwnd:
        return ""
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(128)
        ctypes.windll.user32.GetClassNameW(hwnd, buf, 128)
        return buf.value or ""
    except Exception:
        return ""


def read_control_text(hwnd: int, timeout_ms: int = 150) -> str | None:
    """입력창 글자. 브라우저처럼 글자를 내주지 않는 창은 None."""
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        WM_GETTEXT, WM_GETTEXTLENGTH, SMTO_ABORTIFHUNG = 0x000D, 0x000E, 0x0002
        result = ctypes.c_size_t(0)
        if not user32.SendMessageTimeoutW(
            wintypes.HWND(hwnd), WM_GETTEXTLENGTH, 0, 0, SMTO_ABORTIFHUNG,
            timeout_ms, ctypes.byref(result),
        ):
            return None
        n = int(result.value)
        if n <= 0 or n > 20000:
            return None
        buf = ctypes.create_unicode_buffer(n + 1)
        if not user32.SendMessageTimeoutW(
            wintypes.HWND(hwnd), WM_GETTEXT, n + 1, buf, SMTO_ABORTIFHUNG,
            timeout_ms, ctypes.byref(result),
        ):
            return None
        return buf.value
    except Exception:
        return None


def ime_hangul_mode(foreground_hwnd: int, timeout_ms: int = 100) -> bool:
    """포커스 창 IME 가 한글 모드인지 (IME_CMODE_NATIVE)."""
    if sys.platform != "win32" or not foreground_hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        ime_wnd = ctypes.windll.imm32.ImmGetDefaultIMEWnd(wintypes.HWND(foreground_hwnd))
        if not ime_wnd:
            return False
        WM_IME_CONTROL, IMC_GETCONVERSIONMODE, SMTO_ABORTIFHUNG = 0x0283, 0x0001, 0x0002
        result = ctypes.c_size_t(0)
        if not ctypes.windll.user32.SendMessageTimeoutW(
            wintypes.HWND(ime_wnd), WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0,
            SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(result),
        ):
            return False
        return bool(int(result.value) & 0x0001)
    except Exception:
        return False
