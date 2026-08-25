"""Windows subprocess — 콘솔 창 없이 백그라운드 실행."""

from __future__ import annotations

import subprocess
import sys
from typing import Any


def no_window_kwargs(*, extra_creationflags: int = 0) -> dict[str, Any]:
    """subprocess.run/Popen용 — 모니터에 터미널이 안 뜨게.

    extra_creationflags: CREATE_NEW_PROCESS_GROUP 등 CREATE_NO_WINDOW와 OR할 플래그.
    """
    if sys.platform != "win32":
        return {}
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) | int(extra_creationflags)
    kw: dict[str, Any] = {"creationflags": flags}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kw["startupinfo"] = si
    except Exception:
        pass
    return kw
