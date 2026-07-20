"""UI Live Activity 스트림용 콜백 싱크 (비-PyQt, assistant·automation 계층에서 import 가능)."""

from __future__ import annotations

import threading
from collections.abc import Callable

_lock = threading.Lock()
_sink: Callable[[str], None] | None = None


def register_activity_sink(cb: Callable[[str], None] | None) -> None:
    """MainWindow가 UiActivityHub로 연결한다. None이면 스트림 비활성."""
    global _sink
    with _lock:
        _sink = cb


def push_activity_line(message: str) -> None:
    """스레드 안전: 등록된 싱크가 없으면 무시."""
    if not (message and message.strip()):
        return
    with _lock:
        cb = _sink
    if cb is None:
        return
    try:
        cb(message.strip())
    except Exception:
        pass
