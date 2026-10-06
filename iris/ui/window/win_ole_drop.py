"""Explorer → Iris 파일 드롭.

Qt가 frameless 메인 HWND에 등록하는 IDropTarget은 탐색기 DragEnter를
QDragEnterEvent로 넘기지 않고 DROPEFFECT_NONE을 돌려, 커서가 금지 표시로
남는다. 여기 타깃은 CF_HDROP을 동기적으로 Copy로 받고, 경로는 기존
``_attach_os_drop_paths``로만 넘긴다.

WM_DROPFILES / nativeEvent / WNDPROC는 쓰지 않는다.
"""

from __future__ import annotations

import sys
from ctypes import (
    POINTER,
    WINFUNCTYPE,
    byref,
    c_long,
    c_uint32,
    c_ulong,
    c_void_p,
    cast,
    create_unicode_buffer,
)
from ctypes import wintypes
from pathlib import Path

S_OK = 0
E_NOINTERFACE = 0x80004002
DROPEFFECT_NONE = 0
DROPEFFECT_COPY = 1
CF_HDROP = 15
TYMED_HGLOBAL = 1
DVASPECT_CONTENT = 1

_DATA_GET = WINFUNCTYPE(c_ulong, c_void_p, c_void_p, c_void_p)


def _log(line: str) -> None:
    try:
        log_dir = Path.home() / ".iris-light" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        from time import strftime

        if line.startswith("[ERROR]"):
            text = f"[DragDrop]{line}"
        elif line.startswith("[DragDrop]"):
            text = line
        else:
            text = f"[DragDrop] {line}"
        with (log_dir / "dnd.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{strftime('%H:%M:%S')} {text}\n")
    except Exception:
        pass


def _ole_prop(hwnd: int) -> int:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.GetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        user32.GetPropW.restype = wintypes.HANDLE
        return int(user32.GetPropW(wintypes.HWND(int(hwnd)), "OleDropTargetInterface") or 0)
    except Exception:
        return 0


def _paths_from_data_object(data: int) -> list[str]:
    """IDataObject에서 CF_HDROP 로컬 경로. 없으면 빈 목록."""
    if not data:
        return []
    try:
        import ctypes

        class FORMATETC(ctypes.Structure):
            _fields_ = [
                ("cfFormat", wintypes.WORD),
                ("ptd", c_void_p),
                ("dwAspect", wintypes.DWORD),
                ("lindex", c_long),
                ("tymed", wintypes.DWORD),
            ]

        class STGMEDIUM(ctypes.Structure):
            _fields_ = [
                ("tymed", wintypes.DWORD),
                ("hGlobal", c_void_p),
                ("pUnkForRelease", c_void_p),
            ]

        vtbl = cast(data, POINTER(POINTER(c_void_p)))
        get_data = cast(vtbl[0][3], _DATA_GET)
        fmt = FORMATETC(CF_HDROP, None, DVASPECT_CONTENT, -1, TYMED_HGLOBAL)
        medium = STGMEDIUM()
        hr = get_data(c_void_p(data), byref(fmt), byref(medium))
        paths: list[str] = []
        if hr == S_OK and medium.hGlobal:
            shell32 = ctypes.windll.shell32
            shell32.DragQueryFileW.argtypes = [c_void_p, c_uint32, wintypes.LPWSTR, c_uint32]
            shell32.DragQueryFileW.restype = c_uint32
            count = int(shell32.DragQueryFileW(medium.hGlobal, 0xFFFFFFFF, None, 0))
            for index in range(count):
                buf = create_unicode_buffer(32768)
                shell32.DragQueryFileW(medium.hGlobal, index, buf, len(buf))
                text = buf.value.strip()
                if text:
                    paths.append(text)
            ole32 = ctypes.windll.ole32
            ole32.ReleaseStgMedium.argtypes = [c_void_p]
            ole32.ReleaseStgMedium(byref(medium))
        if paths:
            return paths
        user32 = ctypes.windll.user32
        user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
        user32.RegisterClipboardFormatW.restype = wintypes.UINT
        cf = int(user32.RegisterClipboardFormatW("FileNameW") or 0)
        if not cf:
            return []
        fmt2 = FORMATETC(cf, None, DVASPECT_CONTENT, -1, TYMED_HGLOBAL)
        medium2 = STGMEDIUM()
        if get_data(c_void_p(data), byref(fmt2), byref(medium2)) != S_OK or not medium2.hGlobal:
            return []
        kernel32 = ctypes.windll.kernel32
        kernel32.GlobalLock.argtypes = [c_void_p]
        kernel32.GlobalLock.restype = c_void_p
        kernel32.GlobalUnlock.argtypes = [c_void_p]
        ptr = kernel32.GlobalLock(medium2.hGlobal)
        text = ctypes.wstring_at(ptr).strip() if ptr else ""
        kernel32.GlobalUnlock(medium2.hGlobal)
        ole32 = ctypes.windll.ole32
        ole32.ReleaseStgMedium.argtypes = [c_void_p]
        ole32.ReleaseStgMedium(byref(medium2))
        return [text] if text else []
    except Exception as exc:
        _log(f"path extract failed {exc!r}")
        return []


class _ExplorerDropTarget:
    """HWND에 등록되는 IDropTarget. 파일만 Copy, 나머지는 None."""

    def __init__(self, host: object, *, target_name: str = "main") -> None:
        self.host = host
        self.target_name = target_name
        self.ref = 1
        self._entered = False
        qi = WINFUNCTYPE(c_ulong, c_void_p, c_void_p, POINTER(c_void_p))(self._qi)
        add = WINFUNCTYPE(c_ulong, c_void_p)(self._add)
        rel = WINFUNCTYPE(c_ulong, c_void_p)(self._rel)
        enter = WINFUNCTYPE(c_ulong, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p)(self._enter_raw)
        over = WINFUNCTYPE(c_ulong, c_void_p, c_void_p, c_void_p, c_void_p)(self._over_raw)
        leave = WINFUNCTYPE(c_ulong, c_void_p)(self._leave)
        drop = WINFUNCTYPE(c_ulong, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p)(self._drop_raw)
        self._cbs = (qi, add, rel, enter, over, leave, drop)
        self.vtbl = (c_void_p * len(self._cbs))(*(cast(cb, c_void_p) for cb in self._cbs))
        self.slot = (c_void_p * 1)(cast(self.vtbl, c_void_p))
        import ctypes

        self.addr = int(ctypes.addressof(self.slot))
        self.this = c_void_p(self.addr)

    def _qi(self, this, iid, ppv):
        import ctypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        got = cast(iid, POINTER(GUID)).contents
        # IUnknown / IDropTarget
        if got.Data1 in (0x00000000, 0x00000122):
            ppv[0] = this
            self.ref += 1
            return S_OK
        ppv[0] = None
        return E_NOINTERFACE

    def _add(self, this):
        self.ref += 1
        return self.ref

    def _rel(self, this):
        self.ref = max(0, self.ref - 1)
        return self.ref

    def _log_files(self, paths: list[str]) -> None:
        hwnd = 0
        try:
            hwnd = int(self.host.winId())  # type: ignore[attr-defined]
        except Exception:
            hwnd = 0
        _log("source=explorer")
        _log(f"target={self.target_name}")
        _log(f"hwnd={hwnd}")
        _log(f"cf_hdrop={bool(paths)}")
        _log(f"paths={list(paths)}")
        for path in paths:
            _log(f"filename={Path(path).name}")

    def _notify(self, phase: str, paths: list[str]) -> None:
        fn = getattr(self.host, "_on_explorer_file_drag", None)
        if not callable(fn):
            return
        try:
            fn(phase, paths)
        except Exception as exc:
            _log(f"notify {phase} failed {exc!r}")

    def _write_effect(self, effect, value: int) -> None:
        if not effect:
            return
        try:
            cast(int(effect), POINTER(c_uint32))[0] = int(value)
        except Exception as exc:
            _log(f"effect write failed {exc!r}")

    def _enter_raw(self, this, data, key, pt, effect):
        _log("callback DragEnter")
        paths = _paths_from_data_object(int(data or 0))
        if not paths:
            _log("OS drag entered window urls=0")
            _log("[ERROR] stage=drag_enter")
            _log("[ERROR] reason=cf_hdrop empty")
            self._write_effect(effect, DROPEFFECT_NONE)
            return S_OK
        self._write_effect(effect, DROPEFFECT_COPY)
        self._entered = True
        self._log_files(paths)
        self._notify("enter", paths)
        return S_OK

    def _over_raw(self, this, key, pt, effect):
        self._write_effect(effect, DROPEFFECT_COPY if self._entered else DROPEFFECT_NONE)
        if self._entered:
            self._notify("move", [])
        return S_OK

    def _leave(self, this):
        if self._entered:
            _log("OS drag left window")
            self._notify("leave", [])
        self._entered = False
        return S_OK

    def _drop_raw(self, this, data, key, pt, effect):
        paths = _paths_from_data_object(int(data or 0))
        self._entered = False
        if not paths:
            self._write_effect(effect, DROPEFFECT_NONE)
            _log("[ERROR] stage=drop")
            _log("[ERROR] reason=cf_hdrop empty")
            self._notify("leave", [])
            return S_OK
        self._write_effect(effect, DROPEFFECT_COPY)
        self._log_files(paths)
        _log("attach_start")
        self._notify("drop", paths)
        return S_OK


_DRAGDROP_E_ALREADYREGISTERED = 0x80040101


def _owned_target(host: object, target_name: str) -> _ExplorerDropTarget:
    current = getattr(host, "_explorer_ole_target", None)
    if isinstance(current, _ExplorerDropTarget):
        current.target_name = target_name
        return current
    target = _ExplorerDropTarget(host, target_name=target_name)
    setattr(host, "_explorer_ole_target", target)
    return target


def _bind_ole32():
    import ctypes

    ole32 = ctypes.windll.ole32
    ole32.RegisterDragDrop.argtypes = [wintypes.HWND, c_void_p]
    ole32.RegisterDragDrop.restype = c_ulong
    ole32.RevokeDragDrop.argtypes = [wintypes.HWND]
    ole32.RevokeDragDrop.restype = c_ulong
    return ole32


def _register_hwnd(hwnd: int, target: _ExplorerDropTarget, *, label: str) -> bool:
    """같은 HWND·같은 타깃이면 RegisterDragDrop을 다시 호출하지 않는다."""
    ours = int(getattr(target, "addr", 0) or 0)
    if ours and _ole_prop(int(hwnd)) == ours:
        return True
    ole32 = _bind_ole32()
    prev = _ole_prop(int(hwnd))
    ole32.RevokeDragDrop(wintypes.HWND(int(hwnd)))
    hr = int(ole32.RegisterDragDrop(wintypes.HWND(int(hwnd)), target.this) or 0)
    if hr == _DRAGDROP_E_ALREADYREGISTERED:
        ole32.RevokeDragDrop(wintypes.HWND(int(hwnd)))
        hr = int(ole32.RegisterDragDrop(wintypes.HWND(int(hwnd)), target.this) or 0)
    if hr != S_OK:
        _log("[ERROR] stage=register")
        _log(f"[ERROR] reason=hwnd={int(hwnd)} hr=0x{hr & 0xFFFFFFFF:08x} target={label}")
        return False
    _log(
        f"RegisterDragDrop target={label} hwnd={int(hwnd)} "
        f"prev_ole={prev} ole={_ole_prop(int(hwnd))}"
    )
    return True


def _child_hwnds_with_drop(root: int) -> list[int]:
    import ctypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lp):
        child = int(hwnd)
        ole = _ole_prop(child)
        # Include our existing child targets too. Otherwise the next refresh
        # treats them as removed and revokes WebEngine's drop registration.
        if ole:
            found.append(child)
        return True

    user32.EnumChildWindows(wintypes.HWND(int(root)), _cb, 0)
    return found


def _revoke_hwnds(hwnds) -> None:
    if not hwnds:
        return
    try:
        ole32 = _bind_ole32()
        for window in hwnds:
            try:
                ole32.RevokeDragDrop(wintypes.HWND(int(window)))
            except Exception:
                continue
    except Exception:
        return


def ensure_explorer_drop_targets(hwnd: int, host: object, *, target: str = "main") -> bool:
    """루트 HWND와, 다른 OLE 타깃을 가진 자식 HWND만 등록한다."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        drop = _owned_target(host, target)
        ours = int(getattr(drop, "addr", 0) or 0)
        hwnds = [int(hwnd)]
        hwnds.extend(h for h in _child_hwnds_with_drop(int(hwnd)) if h not in hwnds)
        prev = set(getattr(host, "_explorer_ole_hwnds", ()))
        _revoke_hwnds(prev - set(hwnds))
        root_ok = _register_hwnd(int(hwnd), drop, label=target)
        for child in hwnds[1:]:
            _register_hwnd(child, drop, label=target)
        if not root_ok:
            _restore_qt_drop(host)
            return False
        setattr(host, "_explorer_ole_hwnds", set(hwnds))
        destroyed = getattr(host, "destroyed", None)
        if destroyed is not None and not getattr(host, "_explorer_ole_revoke", False):

            def _revoke(*_args, window_host=host) -> None:
                _revoke_hwnds(getattr(window_host, "_explorer_ole_hwnds", ()))

            try:
                destroyed.connect(_revoke)
                setattr(host, "_explorer_ole_revoke", True)
            except Exception:
                pass
        return _ole_prop(int(hwnd)) == ours
    except Exception as exc:
        _log("[ERROR] stage=register")
        _log(f"[ERROR] reason={exc!r}")
        _restore_qt_drop(host)
        return False


def install_explorer_drop_target(hwnd: int, host: object, *, target: str = "main") -> bool:
    """Qt 타깃을 걷어내고 탐색기 파일 드롭을 받는다. 같은 HWND면 재등록하지 않는다."""
    return ensure_explorer_drop_targets(hwnd, host, target=target)


def _restore_qt_drop(host: object) -> None:
    toggle = getattr(host, "setAcceptDrops", None)
    if not callable(toggle):
        return
    try:
        toggle(False)
        toggle(True)
    except Exception:
        return


def drag_hdrop_onto(hwnd: int, paths: list[str]) -> int:
    """CF_HDROP DoDragDrop. 자가 점검용. 반환값은 마지막으로 본 drop effect."""
    import ctypes
    from ctypes import c_int, c_ushort

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", c_ulong),
            ("Data2", c_ushort),
            ("Data3", c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class FORMATETC(ctypes.Structure):
        _fields_ = [
            ("cfFormat", c_ushort),
            ("ptd", c_void_p),
            ("dwAspect", wintypes.DWORD),
            ("lindex", c_long),
            ("tymed", wintypes.DWORD),
        ]

    class STGMEDIUM(ctypes.Structure):
        _fields_ = [
            ("tymed", wintypes.DWORD),
            ("hGlobal", c_void_p),
            ("pUnkForRelease", c_void_p),
        ]

    kernel32 = ctypes.windll.kernel32
    ole32 = ctypes.windll.ole32
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = c_void_p
    kernel32.GlobalLock.argtypes = [c_void_p]
    kernel32.GlobalLock.restype = c_void_p
    kernel32.GlobalSize.argtypes = [c_void_p]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalUnlock.argtypes = [c_void_p]
    payload = ("\0".join(paths) + "\0\0").encode("utf-16-le")
    raw = (20).to_bytes(4, "little") + bytes(12) + (1).to_bytes(4, "little") + payload
    hglob = kernel32.GlobalAlloc(0x0002, len(raw))
    locked = kernel32.GlobalLock(hglob)
    ctypes.memmove(locked, raw, len(raw))
    kernel32.GlobalUnlock(hglob)
    effects: list[int] = []

    class Data:
        def __init__(self) -> None:
            self.ref = 1
            qi = WINFUNCTYPE(c_long, c_void_p, POINTER(GUID), POINTER(c_void_p))(self.qi)
            add = WINFUNCTYPE(c_ulong, c_void_p)(self.add)
            rel = WINFUNCTYPE(c_ulong, c_void_p)(self.rel)
            get = WINFUNCTYPE(c_long, c_void_p, POINTER(FORMATETC), POINTER(STGMEDIUM))(self.get)
            qget = WINFUNCTYPE(c_long, c_void_p, POINTER(FORMATETC))(self.qget)
            no2 = WINFUNCTYPE(c_long, c_void_p, c_void_p)(lambda *_: 0x80004001)
            no3 = WINFUNCTYPE(c_long, c_void_p, c_void_p, c_void_p)(lambda *_: 0x80004001)
            no4 = WINFUNCTYPE(c_long, c_void_p, c_void_p, c_void_p, c_void_p)(lambda *_: 0x80004001)
            cbs = (qi, add, rel, get, no3, qget, no2, no4, no2, no2, no2, no2)
            self._keep = cbs
            self.vtbl = (c_void_p * 12)(*(cast(cb, c_void_p) for cb in cbs))
            self.slot = (c_void_p * 1)(cast(self.vtbl, c_void_p))
            self.this = ctypes.addressof(self.slot)

        def add(self, this):
            self.ref += 1
            return self.ref

        def rel(self, this):
            self.ref -= 1
            return self.ref

        def qi(self, this, iid, ppv):
            if iid.contents.Data1 in (0, 0x10E):
                ppv[0] = this
                self.ref += 1
                return S_OK
            ppv[0] = None
            return E_NOINTERFACE

        def qget(self, this, fmt):
            if fmt.contents.cfFormat == CF_HDROP and (fmt.contents.tymed & TYMED_HGLOBAL):
                return S_OK
            return 0x80040064

        def get(self, this, fmt, medium):
            if fmt.contents.cfFormat != CF_HDROP or not (fmt.contents.tymed & TYMED_HGLOBAL):
                return 0x80040064
            size = kernel32.GlobalSize(c_void_p(hglob))
            clone = kernel32.GlobalAlloc(0x0002, size)
            src = kernel32.GlobalLock(c_void_p(hglob))
            dst = kernel32.GlobalLock(c_void_p(clone))
            ctypes.memmove(dst, src, size)
            kernel32.GlobalUnlock(c_void_p(hglob))
            kernel32.GlobalUnlock(c_void_p(clone))
            medium.contents.tymed = TYMED_HGLOBAL
            medium.contents.hGlobal = clone
            medium.contents.pUnkForRelease = None
            return S_OK

    class Src:
        def __init__(self) -> None:
            self.n = 0
            qi = WINFUNCTYPE(c_long, c_void_p, POINTER(GUID), POINTER(c_void_p))(self.qi)
            add = WINFUNCTYPE(c_ulong, c_void_p)(lambda this: 1)
            rel = WINFUNCTYPE(c_ulong, c_void_p)(lambda this: 1)
            qcd = WINFUNCTYPE(c_long, c_void_p, c_int, wintypes.DWORD)(self.qcd)
            fb = WINFUNCTYPE(c_long, c_void_p, wintypes.DWORD)(self.fb)
            cbs = (qi, add, rel, qcd, fb)
            self._keep = cbs
            self.vtbl = (c_void_p * 5)(*(cast(cb, c_void_p) for cb in cbs))
            self.slot = (c_void_p * 1)(cast(self.vtbl, c_void_p))
            self.this = ctypes.addressof(self.slot)

        def qi(self, this, iid, ppv):
            if iid.contents.Data1 in (0, 0x121):
                ppv[0] = this
                return S_OK
            ppv[0] = None
            return E_NOINTERFACE

        def qcd(self, this, escape, key):
            self.n += 1
            if escape or self.n >= 4:
                return 0x00040100
            return S_OK

        def fb(self, this, effect):
            effects.append(int(effect))
            return 0x00040102

    data = Data()
    src = Src()
    effect = wintypes.DWORD(0)
    ole32.DoDragDrop.argtypes = [c_void_p, c_void_p, wintypes.DWORD, POINTER(wintypes.DWORD)]
    ole32.DoDragDrop.restype = c_long
    hr = int(ole32.DoDragDrop(data.this, src.this, DROPEFFECT_COPY, byref(effect)) or 0)
    chosen = int(effect.value) or (effects[-1] if effects else 0)
    _log(f"DoDragDrop hr=0x{hr & 0xFFFFFFFF:08x} effect={chosen} feedback={effects}")
    return chosen
