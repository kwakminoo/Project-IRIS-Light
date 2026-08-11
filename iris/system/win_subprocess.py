"""Windows subprocess — 콘솔 창 없이 백그라운드 실행."""

from __future__ import annotations

import subprocess
import sys
from typing import Any


def no_window_kwargs() -> dict[str, Any]:
    """subprocess.run/Popen용 — 모니터에 터미널이 안 뜨게."""
    if sys.platform != "win32":
        return {}
    kw: dict[str, Any] = {
        "creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
    }
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kw["startupinfo"] = si
    except Exception:
        pass
    return kw
