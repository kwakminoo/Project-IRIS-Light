"""창 검색·포커스·이동·크기 (Windows)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import List


@dataclass
class WindowInfo:
    title: str
    left: int
    top: int
    width: int
    height: int
    hwnd: int = 0  # Windows HWND (0이면 미상)
    minimized: bool = False  # 최소화 상태 — 좌표는 복원 시 위치(rcNormalPosition)


def get_active_window_title() -> str:
    """현재 포커스 창 제목 (실패 시 빈 문자열)."""
    try:
        import pygetwindow as gw  # type: ignore

        w = gw.getActiveWindow()
        if w and w.title:
            return str(w.title)
    except Exception:
        pass
    return ""


def list_window_titles() -> List[str]:
    """제목 목록 (가능할 때만)."""
    return [w.title for w in list_visible_windows()]


def list_visible_windows() -> List[WindowInfo]:
    """Alt+Tab에 뜨는 창 목록 — hwnd 포함, 숨김 제외 (Windows 우선).

    최소화된 창도 Alt+Tab에는 뜨므로 포함하되 minimized=True로 표시한다."""
    if sys.platform == "win32":
        wins = _list_via_win32()
        if wins:
            return wins
    if sys.platform == "darwin":
        wins = _list_via_macos_quartz()
        if wins:
            return wins
    return _list_via_pygetwindow()


def _list_via_macos_quartz() -> List[WindowInfo]:
    """pygetwindow의 macOS 백엔드는 getAllWindows()가 없어 항상 빈 리스트를 반환한다
    (창 목록·크기는 미구현 stub) — Quartz CGWindowList API로 직접 조회."""
    try:
        import Quartz  # type: ignore
    except Exception:
        return []
    try:
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListExcludeDesktopElements | Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
        )
    except Exception:
        return []

    results: List[WindowInfo] = []
    for win in windows:
        try:
            if win.get("kCGWindowLayer", 0) != 0:
                continue
            title = (win.get(Quartz.kCGWindowName, "") or "").strip()
            owner = (win.get(Quartz.kCGWindowOwnerName, "") or "").strip()
            label = title or owner
            if not label:
                continue
            bounds = win.get("kCGWindowBounds")
            if not bounds:
                continue
            w, h = int(bounds["Width"]), int(bounds["Height"])
            if w <= 0 or h <= 0:
                continue
            results.append(
                WindowInfo(label, int(bounds["X"]), int(bounds["Y"]), w, h, 0)
            )
        except Exception:
            continue
    return results


def list_macos_windows_for_pids(pids: set) -> List[dict]:
    """PID 집합 소유 창 목록 (macOS) — hwnd 자리엔 CGWindowNumber를 담는다.

    IDE Companion 타일링처럼 특정 프로세스가 띄운 창만 골라야 할 때 사용
    (ide_launcher.list_ide_windows의 macOS 경로에서 사용)."""
    if sys.platform != "darwin" or not pids:
        return []
    try:
        import Quartz  # type: ignore
    except Exception:
        return []
    try:
        # OnScreenOnly는 다른 space(가상 데스크톱)에 있는 창을 놓친다 — IDE 타일링은
        # 다른 space에 떠 있는 창도 찾아서 타일해야 하므로 전체 창을 조회한다.
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
    except Exception:
        return []

    found: List[dict] = []
    for win in windows:
        try:
            pid = int(win.get(Quartz.kCGWindowOwnerPID, 0) or 0)
            if pid not in pids:
                continue
            if win.get("kCGWindowLayer", 0) != 0:
                continue
            title = (win.get(Quartz.kCGWindowName, "") or "").strip()
            if not title:
                continue
            bounds = win.get("kCGWindowBounds")
            if not bounds:
                continue
            w, h = int(bounds["Width"]), int(bounds["Height"])
            if w < 200 or h < 120:
                continue
            number = int(win.get("kCGWindowNumber", 0) or 0)
            found.append(
                {"hwnd": number, "pid": pid, "title": title, "score": w * h, "w": w, "h": h}
            )
        except Exception:
            continue
    return found


def is_macos_window_number_alive(window_number: int) -> bool:
    """CGWindowNumber가 아직 존재하는 창인지 (companion 타일 재사용 판단용)."""
    if sys.platform != "darwin" or not window_number:
        return False
    try:
        import Quartz  # type: ignore

        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        return any(int(w.get("kCGWindowNumber", 0) or 0) == int(window_number) for w in windows)
    except Exception:
        return False


# Alt+Tab 판정용 Win32 상수
_GA_ROOTOWNER = 3
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_DWMWA_CLOAKED = 14

_ALT_TAB_API: dict | None = None


def _alt_tab_api() -> dict:
    """Alt+Tab 판정에 쓰는 Win32 함수 — 최초 1회만 로드 (실패 시 빈 dict)."""
    global _ALT_TAB_API
    if _ALT_TAB_API is not None:
        return _ALT_TAB_API

    api: dict = {}
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetLastActivePopup.argtypes = [wintypes.HWND]
        user32.GetLastActivePopup.restype = wintypes.HWND
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL

        # GetWindowLongPtrW는 64비트에만 존재 — 32비트에선 GetWindowLongW로 폴백
        get_exstyle = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
        get_exstyle.argtypes = [wintypes.HWND, ctypes.c_int]
        get_exstyle.restype = ctypes.c_ssize_t

        api = {"ctypes": ctypes, "user32": user32, "get_exstyle": get_exstyle}

        try:
            dwmapi = ctypes.windll.dwmapi
            dwmapi.DwmGetWindowAttribute.argtypes = [
                wintypes.HWND,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long  # HRESULT
            api["dwmapi"] = dwmapi
        except Exception:
            pass  # DWM 없는 환경 — 클로킹 검사만 생략
    except Exception:
        api = {}

    _ALT_TAB_API = api
    return api


def _is_cloaked(hwnd: int, api: dict) -> bool:
    """DWM이 감춘 창인지 — 정지된 UWP 앱, 다른 가상 데스크톱의 창이 여기 걸린다.

    '설정' 같은 UWP는 ApplicationFrameHost의 프레임 창과 실제 코어 창이
    같은 제목으로 둘 다 잡히는데, 코어 창 쪽이 클로킹돼 있어 이걸로 걸러진다."""
    dwmapi = api.get("dwmapi")
    if not dwmapi:
        return False
    ctypes = api["ctypes"]
    val = ctypes.c_int(0)
    try:
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd, _DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val)
        )
    except Exception:
        return False
    return hr == 0 and val.value != 0


def _is_alt_tab_window(hwnd: int) -> bool:
    """Alt+Tab 목록에 뜨는 창인지 — 셸이 쓰는 판정과 같은 규칙.

    소유자 체인의 최상위가 자기 자신이어야 하고(대화상자·팝업 제외),
    WS_EX_TOOLWINDOW가 없어야 하며(NVIDIA 오버레이 같은 도구 창 제외),
    DWM에 클로킹돼 있지 않아야 한다. 판정 불가 환경에선 True(기존 동작)."""
    api = _alt_tab_api()
    if not api:
        return True

    user32 = api["user32"]
    try:
        if _is_cloaked(hwnd, api):
            return False

        # 소유자 체인 최상위의 마지막 활성 팝업이 자기 자신이어야 한다
        walk = None
        cur = user32.GetAncestor(hwnd, _GA_ROOTOWNER)
        while cur != walk:
            walk = cur
            cur = user32.GetLastActivePopup(walk)
            if user32.IsWindowVisible(cur):
                break
        if walk != hwnd:
            return False

        if api["get_exstyle"](hwnd, _GWL_EXSTYLE) & _WS_EX_TOOLWINDOW:
            return False
    except Exception:
        return True
    return True


def _list_via_win32() -> List[WindowInfo]:
    try:
        import win32gui  # type: ignore
    except Exception:
        return []

    results: List[WindowInfo] = []

    def _cb(hwnd: int, _arg: object) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if not _is_alt_tab_window(hwnd):  # Alt+Tab에 안 뜨는 창 제외
                return True
            title = win32gui.GetWindowText(hwnd) or ""
            if not title.strip():
                return True
            minimized = bool(win32gui.IsIconic(hwnd))
            # 최소화 창의 GetWindowRect는 실제 위치가 아니므로(작업표시줄 쪽 좌표)
            # 복원 시 위치인 rcNormalPosition을 쓴다 — 타일링·캡처가 엉뚱한
            # 화면 영역을 잡지 않도록.
            rect = None
            if minimized:
                try:
                    rect = win32gui.GetWindowPlacement(hwnd)[4]
                except Exception:
                    rect = None
            if rect is None:
                rect = win32gui.GetWindowRect(hwnd)
            left, top, right, bot = rect
            w, h = right - left, bot - top
            if w <= 0 or h <= 0:
                return True
            # 시스템 셸 창 일부 제외
            if title in ("Program Manager", "Windows Input Experience"):
                return True
            results.append(
                WindowInfo(title, int(left), int(top), int(w), int(h), int(hwnd), minimized)
            )
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        return []
    return results


def _list_via_pygetwindow() -> List[WindowInfo]:
    try:
        import pygetwindow as gw  # type: ignore
    except Exception:
        return []
    out: List[WindowInfo] = []
    try:
        for w in gw.getAllWindows():
            if not w.title:
                continue
            hwnd = int(getattr(w, "_hWnd", 0) or 0)
            out.append(
                WindowInfo(w.title, int(w.left), int(w.top), int(w.width), int(w.height), hwnd)
            )
    except Exception:
        pass
    return out


def find_windows_by_title_substring(sub: str) -> List[WindowInfo]:
    try:
        import pygetwindow as gw  # type: ignore
    except Exception:
        return []
    out: List[WindowInfo] = []
    sub_l = sub.lower()
    try:
        for w in gw.getAllWindows():
            if not w.title:
                continue
            if sub_l in w.title.lower():
                hwnd = int(getattr(w, "_hWnd", 0) or 0)
                out.append(
                    WindowInfo(
                        w.title,
                        int(w.left),
                        int(w.top),
                        int(w.width),
                        int(w.height),
                        hwnd,
                    )
                )
    except Exception:
        pass
    return out


def focus_and_place(title_sub: str, left: int, top: int, width: int, height: int) -> tuple[bool, str]:
    """첫 매칭 창에 포커스 및 위치/크기."""
    try:
        import pygetwindow as gw  # type: ignore
    except Exception as e:
        return False, f"pygetwindow 없음: {e}"
    try:
        wins = [w for w in gw.getAllWindows() if w.title and title_sub.lower() in w.title.lower()]
        if not wins:
            return False, "창 없음"
        w = wins[0]
        try:
            w.activate()
        except Exception:
            pass
        w.moveTo(left, top)
        w.resizeTo(width, height)
        return True, "ok"
    except Exception as e:
        return False, str(e)


def focus_window_by_hwnd(hwnd: int) -> bool:
    """HWND 기반 포커스 (창 이동 없음). pygetwindow 미사용."""
    if sys.platform != "win32" or hwnd <= 0:
        return False
    try:
        import win32gui  # type: ignore
        import win32con  # type: ignore

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def close_window_by_hwnd(hwnd: int) -> bool:
    """HWND에 WM_CLOSE 전송 — 앱의 정상 종료 루틴을 따름 (강제 종료 아님)."""
    if sys.platform != "win32" or hwnd <= 0:
        return False
    try:
        import win32gui  # type: ignore
        import win32con  # type: ignore

        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return True
    except Exception:
        return False
