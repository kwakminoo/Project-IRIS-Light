"""Alt+Tab 노출 판정 회귀 테스트.

실제 HWND 없이 Win32 호출부를 가짜로 주입해 규칙만 고정한다 —
NVIDIA 오버레이 같은 도구 창, 정지된 UWP('설정')의 클로킹된 창,
대화상자처럼 소유자가 따로 있는 창이 목록에 새어나오지 않아야 한다."""

from __future__ import annotations

import sys
from unittest import TestCase

from iris.automation import window_controller as wc


class _FakeUser32:
    """소유자 체인·가시성·확장 스타일을 딕셔너리로 흉내낸다."""

    def __init__(self, owners: dict, visible: set, popups: dict) -> None:
        self._owners = owners  # hwnd -> 소유자 체인 최상위
        self._visible = visible
        self._popups = popups  # hwnd -> 마지막 활성 팝업

    def GetAncestor(self, hwnd: int, _flag: int) -> int:
        return self._owners.get(hwnd, hwnd)

    def GetLastActivePopup(self, hwnd: int) -> int:
        return self._popups.get(hwnd, hwnd)

    def IsWindowVisible(self, hwnd: int) -> int:
        return 1 if hwnd in self._visible else 0


def _install_fake_api(
    *,
    owners: dict | None = None,
    visible: set | None = None,
    popups: dict | None = None,
    exstyles: dict | None = None,
    cloaked: set | None = None,
) -> None:
    owners = owners or {}
    visible = visible if visible is not None else set()
    popups = popups or {}
    exstyles = exstyles or {}
    cloaked = cloaked or set()

    class _FakeDwm:
        def DwmGetWindowAttribute(self, hwnd, _attr, out_ref, _size):
            out_ref._obj.value = 1 if hwnd in cloaked else 0
            return 0  # S_OK

    class _FakeCtypes:
        class c_int:
            def __init__(self, value: int = 0) -> None:
                self.value = value

        class _Ref:
            def __init__(self, obj) -> None:
                self._obj = obj

        @staticmethod
        def byref(obj):
            return _FakeCtypes._Ref(obj)

        @staticmethod
        def sizeof(_obj) -> int:
            return 4

    wc._ALT_TAB_API = {
        "ctypes": _FakeCtypes,
        "user32": _FakeUser32(owners, visible, popups),
        "get_exstyle": lambda hwnd, _idx: exstyles.get(hwnd, 0),
        "dwmapi": _FakeDwm(),
    }


class AltTabFilterTests(TestCase):
    def tearDown(self) -> None:
        wc._ALT_TAB_API = None  # 다른 테스트에 가짜가 새지 않도록 복구

    def test_plain_top_level_window_is_listed(self) -> None:
        _install_fake_api(visible={100})
        self.assertTrue(wc._is_alt_tab_window(100))

    def test_tool_window_is_excluded(self) -> None:
        """NVIDIA GeForce Overlay 같은 WS_EX_TOOLWINDOW 창."""
        _install_fake_api(visible={200}, exstyles={200: wc._WS_EX_TOOLWINDOW})
        self.assertFalse(wc._is_alt_tab_window(200))

    def test_cloaked_window_is_excluded(self) -> None:
        """정지된 UWP('설정')의 코어 창처럼 DWM이 감춘 창."""
        _install_fake_api(visible={300}, cloaked={300})
        self.assertFalse(wc._is_alt_tab_window(300))

    def test_owned_window_is_excluded(self) -> None:
        """소유자가 따로 있는 대화상자 — 체인 최상위가 자기 자신이 아니다."""
        _install_fake_api(owners={301: 300}, visible={300, 301})
        self.assertFalse(wc._is_alt_tab_window(301))

    def test_owner_is_listed_when_it_owns_a_dialog(self) -> None:
        """대화상자를 띄운 소유자 창은 남아야 한다 — 짝이 통째로 사라지면 안 된다."""
        _install_fake_api(
            owners={300: 300, 301: 300}, visible={300, 301}, popups={300: 301}
        )
        self.assertTrue(wc._is_alt_tab_window(300))
        self.assertFalse(wc._is_alt_tab_window(301))

    def test_missing_win32_api_keeps_window(self) -> None:
        """판정 불가 환경(비-Windows 등)에서는 걸러내지 않는다."""
        wc._ALT_TAB_API = {}
        self.assertTrue(wc._is_alt_tab_window(400))


class _FakeWin32Gui:
    """win32gui 중 _list_via_win32가 쓰는 함수만 흉내낸다."""

    def __init__(self, windows: list[dict]) -> None:
        self._windows = {w["hwnd"]: w for w in windows}

    def EnumWindows(self, cb, arg):
        for hwnd in list(self._windows):
            cb(hwnd, arg)

    def IsWindowVisible(self, hwnd: int) -> int:
        return 1 if self._windows[hwnd].get("visible", True) else 0

    def IsIconic(self, hwnd: int) -> int:
        return 1 if self._windows[hwnd].get("iconic", False) else 0

    def GetWindowText(self, hwnd: int) -> str:
        return self._windows[hwnd].get("title", "")

    def GetWindowRect(self, hwnd: int):
        return self._windows[hwnd]["rect"]

    def GetWindowPlacement(self, hwnd: int):
        # (flags, showCmd, ptMinPosition, ptMaxPosition, rcNormalPosition)
        return (0, 2, (0, 0), (0, 0), self._windows[hwnd]["normal_rect"])


class MinimizedWindowTests(TestCase):
    """최소화된 창도 Alt+Tab에 뜨므로 목록에 남아야 한다."""

    def setUp(self) -> None:
        self._saved = sys.modules.get("win32gui")
        wc._ALT_TAB_API = {}  # Alt+Tab 판정은 통과시키고 최소화 처리만 본다

    def tearDown(self) -> None:
        if self._saved is None:
            sys.modules.pop("win32gui", None)
        else:
            sys.modules["win32gui"] = self._saved
        wc._ALT_TAB_API = None

    def _run(self, windows: list[dict]) -> list:
        sys.modules["win32gui"] = _FakeWin32Gui(windows)
        return wc._list_via_win32()

    def test_minimized_window_is_listed_with_restore_geometry(self) -> None:
        """최소화 창의 GetWindowRect는 엉뚱한 좌표라 rcNormalPosition을 써야 한다."""
        wins = self._run(
            [
                {
                    "hwnd": 10,
                    "title": "톡캘린더 - Chrome",
                    "iconic": True,
                    "rect": (-32000, -32000, -31843, -31975),
                    "normal_rect": (0, 0, 747, 852),
                }
            ]
        )
        self.assertEqual(len(wins), 1)
        self.assertTrue(wins[0].minimized)
        self.assertEqual(
            (wins[0].left, wins[0].top, wins[0].width, wins[0].height), (0, 0, 747, 852)
        )

    def test_normal_window_uses_actual_rect(self) -> None:
        wins = self._run(
            [
                {
                    "hwnd": 11,
                    "title": "Iris Light",
                    "rect": (80, 26, 1360, 826),
                    "normal_rect": (0, 0, 100, 100),
                }
            ]
        )
        self.assertEqual(len(wins), 1)
        self.assertFalse(wins[0].minimized)
        self.assertEqual(
            (wins[0].left, wins[0].top, wins[0].width, wins[0].height), (80, 26, 1280, 800)
        )

    def test_untitled_and_shell_windows_still_excluded(self) -> None:
        wins = self._run(
            [
                {"hwnd": 12, "title": "   ", "rect": (0, 0, 100, 100), "normal_rect": (0, 0, 1, 1)},
                {
                    "hwnd": 13,
                    "title": "Program Manager",
                    "rect": (0, 0, 1440, 900),
                    "normal_rect": (0, 0, 1, 1),
                },
                {
                    "hwnd": 14,
                    "title": "숨김",
                    "visible": False,
                    "rect": (0, 0, 100, 100),
                    "normal_rect": (0, 0, 1, 1),
                },
            ]
        )
        self.assertEqual(wins, [])
