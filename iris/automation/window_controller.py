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
    try:
        import pygetwindow as gw  # type: ignore
    except Exception:
        return []
    try:
        return [w.title for w in gw.getAllWindows() if w.title]
    except Exception:
        return []


def list_visible_windows() -> List[WindowInfo]:
    """가시 최상위 창 목록 — hwnd 포함, 최소화·숨김 제외 (Windows 우선)."""
    if sys.platform == "win32":
        wins = _list_via_win32()
        if wins:
            return wins
    return _list_via_pygetwindow()


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
            if win32gui.IsIconic(hwnd):  # 최소화된 창 제외
                return True
            title = win32gui.GetWindowText(hwnd) or ""
            if not title.strip():
                return True
            left, top, right, bot = win32gui.GetWindowRect(hwnd)
            w, h = right - left, bot - top
            if w <= 0 or h <= 0:
                return True
            # 시스템 셸 창 일부 제외
            if title in ("Program Manager", "Windows Input Experience"):
                return True
            results.append(WindowInfo(title, int(left), int(top), int(w), int(h), int(hwnd)))
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
