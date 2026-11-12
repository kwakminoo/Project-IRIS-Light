"""Iris GUI 단일 인스턴스 — control_port 경쟁과 이중 sidecar를 막는다."""

from __future__ import annotations

import atexit
import hashlib
import os
from pathlib import Path

_LOCK_FH = None
_MUTEX_HANDLE = None

_ERROR_ALREADY_EXISTS = 183
_WAIT_OBJECT_0 = 0
_WAIT_ABANDONED = 128
_WAIT_TIMEOUT = 258


def _mutex_name(data_dir: Path) -> str:
    digest = hashlib.sha256(str(data_dir.resolve()).encode("utf-8")).hexdigest()[:24]
    # Global\\ so elevated and non-elevated relaunches share one mutex.
    return f"Global\\IrisLightGUI_{digest}"


def _release() -> None:
    global _LOCK_FH, _MUTEX_HANDLE
    if os.name == "nt" and _MUTEX_HANDLE is not None:
        try:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(_MUTEX_HANDLE)
        except Exception:
            pass
        _MUTEX_HANDLE = None
    if _LOCK_FH is None:
        return
    try:
        if os.name != "nt":
            import fcntl

            fcntl.flock(_LOCK_FH.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        _LOCK_FH.close()
    except Exception:
        pass
    _LOCK_FH = None


def _record_pid(root: Path) -> None:
    global _LOCK_FH
    path = root / "iris_gui.lock"
    fh = open(path, "a+", encoding="utf-8")
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    _LOCK_FH = fh


def _acquire_windows(root: Path) -> tuple[bool, str]:
    """Named mutex is the uniqueness token; lock file only records PID."""
    global _MUTEX_HANDLE
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    if _MUTEX_HANDLE is not None:
        return False, "Iris가 이미 실행 중입니다. 기존 창을 사용하세요."

    name = _mutex_name(root)
    ctypes.set_last_error(0)
    # Classic singleton: create with ownership. Existing name → we do not own it.
    handle = kernel32.CreateMutexW(None, True, name)
    if not handle:
        raise OSError(f"CreateMutexW failed: {ctypes.get_last_error()}")

    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        # Live holder → TIMEOUT. Dead holder (abandoned) → we take ownership.
        wait = kernel32.WaitForSingleObject(handle, 0)
        if wait == _WAIT_TIMEOUT:
            kernel32.CloseHandle(handle)
            return False, "Iris가 이미 실행 중입니다. 기존 창을 사용하세요."
        if wait not in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            kernel32.CloseHandle(handle)
            raise OSError(f"WaitForSingleObject failed: {wait}")
        # WAIT_ABANDONED / WAIT_OBJECT_0: we own the mutex now.
    # else: created + owned via bInitialOwner=True; no Wait needed.

    _MUTEX_HANDLE = handle
    _record_pid(root)
    atexit.register(_release)
    return True, ""


def _acquire_posix(root: Path) -> tuple[bool, str]:
    global _LOCK_FH
    import fcntl

    path = root / "iris_gui.lock"
    fh = open(path, "a+", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False, "Iris가 이미 실행 중입니다. 기존 창을 사용하세요."
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    _LOCK_FH = fh
    atexit.register(_release)
    return True, ""


def acquire_gui_singleton(*, data_dir: Path | None = None) -> tuple[bool, str]:
    """이미 GUI가 있으면 (False, 안내). 잡으면 (True, '')."""
    root = data_dir or (Path.home() / ".iris-light")
    root.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        return _acquire_windows(root)
    return _acquire_posix(root)


if __name__ == "__main__":
    ok, msg = acquire_gui_singleton()
    assert ok, msg
    ok2, msg2 = acquire_gui_singleton()
    print("gui_singleton ok", ok, msg, ok2, msg2)
