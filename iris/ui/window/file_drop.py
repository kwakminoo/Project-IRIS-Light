"""창 전역 OS 파일/폴더 드롭 — 위젯 트리에 acceptDrops를 심는다."""

from __future__ import annotations

import os
import time
from pathlib import Path
from weakref import WeakSet

from PyQt6.QtWidgets import QWidget


def arm_widget_tree(root: QWidget, filter_obj: object, armed: WeakSet) -> None:
    """자식 포함 setAcceptDrops + eventFilter. OLE 드롭은 acceptDrops 없는 HWND에서 버려진다."""
    if root is None:
        return
    try:
        root.objectName()  # sip 생존 확인
    except RuntimeError:
        return
    stack: list[QWidget] = [root]
    while stack:
        w = stack.pop()
        try:
            w.objectName()
        except RuntimeError:
            continue
        if w in armed:
            continue
        armed.add(w)
        try:
            w.setAcceptDrops(True)
            w.installEventFilter(filter_obj)
            stack.extend(w.findChildren(QWidget))
        except RuntimeError:
            continue


def drop_event_types():
    from PyQt6.QtCore import QEvent

    return (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop)


def log_drop_event(phase: str, mime, *, watched: object | None = None, pos=None) -> None:
    """탐색기 DnD 진단 — ~/.iris-light/logs/dnd.log (항상 1줄, 용량 작음)."""
    try:
        log_dir = Path.home() / ".iris-light" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fmts: list[str] = []
        urls: list[str] = []
        if mime is not None:
            try:
                fmts = [str(f) for f in mime.formats()][:12]
            except Exception:
                pass
            try:
                if mime.hasUrls():
                    urls = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()][:4]
            except Exception:
                pass
        cls = type(watched).__name__ if watched is not None else "-"
        oname = "-"
        try:
            oname = str(getattr(watched, "objectName", lambda: "")() or "-")
        except Exception:
            pass
        pos_s = "-"
        if pos is not None:
            try:
                pos_s = f"{int(pos.x())},{int(pos.y())}"
            except Exception:
                pos_s = str(pos)
        line = (
            f"{time.strftime('%H:%M:%S')} {phase} widget={cls}/{oname} "
            f"pos={pos_s} urls={urls!r} formats={fmts!r}\n"
        )
        with (log_dir / "dnd.log").open("a", encoding="utf-8") as fh:
            fh.write(line)
        if os.environ.get("IRIS_DROP_DEBUG", "").strip() in ("1", "true", "yes"):
            print(f"[iris-dnd] {line}", end="", flush=True)
    except Exception:
        pass


def mime_has_attachable(mime) -> bool:
    from iris.ui.chat.chat_panel import _mime_has_attachable

    return bool(_mime_has_attachable(mime))


def paths_from_mime(mime) -> list[str]:
    from iris.ui.chat.chat_panel import _drop_targets_from_mime, _save_clipboard_image
    from PyQt6.QtGui import QImage

    paths = _drop_targets_from_mime(mime)
    if paths:
        return paths
    if mime is not None and mime.hasImage():
        data = mime.imageData()
        if isinstance(data, QImage) and not data.isNull():
            saved = _save_clipboard_image(data)
            if saved:
                return [saved]
    return []
