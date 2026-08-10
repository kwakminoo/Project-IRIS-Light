"""IRIS 내부 demonstration recorder — Aloha Recorder GUI 비노출."""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from iris.learning.models import LearningEvent, SessionManifest
from iris.learning.paths import session_dir
from iris.learning.privacy import (
    is_password_control_os,
    redact_key_if_needed,
    redact_text_if_needed,
)

log = logging.getLogger("iris.learning.recorder")


def _foreground_info() -> tuple[str, str, int]:
    """(process_name, window_title, hwnd)."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = int(user32.GetForegroundWindow())
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = ""
        try:
            import psutil

            proc = psutil.Process(int(pid.value)).name()
        except Exception:
            proc = ""
        return proc, title, hwnd
    except Exception:
        return "", "", 0


def _screen_metrics() -> tuple[int, int, float]:
    try:
        import mss

        with mss.mss() as sct:
            mon = sct.monitors[1]
            return int(mon["width"]), int(mon["height"]), 1.0
    except Exception:
        return 1920, 1080, 1.0


def _is_password_control() -> bool:
    return is_password_control_os()


class DemonstrationRecorder:
    """화면 + 마우스 + 키보드 + foreground context."""

    def __init__(
        self,
        session_id: str,
        *,
        fps: float = 4.0,
        iris_hwnds: list[int] | None = None,
        on_error: Callable[[str], None] | None = None,
        record_keyboard: bool = True,
        store_key_chars: bool = True,
        hook_backend: str = "auto",
    ) -> None:
        self.session_id = session_id
        self.fps = max(1.0, min(fps, 8.0))
        self.iris_hwnds = set(iris_hwnds or [])
        self._on_error = on_error
        self._record_keyboard = record_keyboard
        self._store_key_chars = store_key_chars
        self._hook_backend = hook_backend
        self._win32_hooks = None
        self._dir = session_dir(session_id)
        self._events: list[LearningEvent] = []
        self._lock = threading.RLock()
        self._running = False
        self._hooks_active = False
        self._t0 = 0.0
        self._video_thread: threading.Thread | None = None
        self._mouse_listener = None
        self._keyboard_listener = None
        self._last_fg = ("", "", 0)
        self._drag_active = False
        self._drag_path: list[tuple[float, float]] = []
        w, h, scale = _screen_metrics()
        self.manifest = SessionManifest(
            session_id=session_id,
            started_at=datetime.now().isoformat(timespec="seconds"),
            screen_width=w,
            screen_height=h,
            scale_factor=scale,
            fps=self.fps,
            iris_hwnds=list(self.iris_hwnds),
        )

    @property
    def directory(self) -> Path:
        return self._dir

    def events_snapshot(self) -> list[LearningEvent]:
        with self._lock:
            return list(self._events)

    def start(self) -> None:
        """hooks는 호출 즉시 켠다 — 시작 버튼 클릭은 manager가 지연 호출."""
        if self._running:
            return
        self._running = True
        self._t0 = time.time()
        self._write_manifest()
        self._start_video()
        self._start_hooks()
        proc, title, hwnd = _foreground_info()
        self._last_fg = (proc, title, hwnd)
        self._append(
            LearningEvent(
                timestamp=0.0,
                event_type="context",
                window_title=title,
                process_name=proc,
                metadata={"kind": "initial_window", "hwnd": hwnd},
            )
        )

    def stop_hooks_first(self) -> None:
        """종료 버튼 클릭이 trace에 안 들어가도록 hooks를 즉시 해제."""
        self._stop_hooks()

    def finalize(self, *, status: str = "finalized") -> SessionManifest:
        self._running = False
        self._stop_hooks()
        if self._video_thread and self._video_thread.is_alive():
            self._video_thread.join(timeout=5.0)
        with self._lock:
            self.manifest.event_count = len(
                [e for e in self._events if not e.exclude_from_trace]
            )
        self.manifest.ended_at = datetime.now().isoformat(timespec="seconds")
        self.manifest.status = status
        events_path = self._dir / "inputs" / "events.json"
        with self._lock:
            payload = [asdict(e) for e in self._events]
        events_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.manifest.events_path = str(events_path)
        video = self._dir / "inputs" / "recording.mp4"
        if video.is_file():
            self.manifest.video_path = str(video)
        self._write_manifest()
        return self.manifest

    def interrupt(self) -> SessionManifest:
        return self.finalize(status="interrupted")

    def _write_manifest(self) -> None:
        path = self._dir / "manifest.json"
        path.write_text(
            json.dumps(asdict(self.manifest), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _rel_ts(self) -> float:
        return max(0.0, time.time() - self._t0)

    def _append(self, event: LearningEvent) -> None:
        # IRIS learning chrome에서 난 입력은 defensive filter
        if event.metadata.get("hwnd") in self.iris_hwnds and event.event_type in {
            "click",
            "double_click",
            "right_click",
            "press",
            "release",
        }:
            # 학습 컨트롤만 제외 — IRIS 본문 사용은 유지. chrome title bar 근처 y는 별도 마킹.
            if event.metadata.get("learning_control"):
                event.exclude_from_trace = True
        with self._lock:
            self._events.append(event)

    def _maybe_window_change(self) -> tuple[str, str]:
        proc, title, hwnd = _foreground_info()
        prev = self._last_fg
        if (proc, title) != (prev[0], prev[1]):
            self._append(
                LearningEvent(
                    timestamp=self._rel_ts(),
                    event_type="window_change",
                    window_title=title,
                    process_name=proc,
                    metadata={"hwnd": hwnd, "prev": {"process": prev[0], "title": prev[1]}},
                )
            )
            self._last_fg = (proc, title, hwnd)
        return proc, title

    def _start_hooks(self) -> None:
        try:
            from pynput import keyboard, mouse
        except ImportError as exc:
            msg = f"pynput 없음 → Win32 폴백 시도 ({exc})"
            log.warning(msg)
            if self._start_win32_hooks():
                return
            if self._on_error:
                self._on_error(msg)
            return

        def on_move(x, y):
            if not self._hooks_active:
                return
            if self._drag_active:
                self._drag_path.append((float(x), float(y)))

        def on_click(x, y, button, pressed):
            if not self._hooks_active:
                return
            self._handle_mouse_button(
                float(x),
                float(y),
                str(button).split(".")[-1].lower(),
                bool(pressed),
            )

        def on_scroll(x, y, dx, dy):
            if not self._hooks_active:
                return
            proc, title = self._maybe_window_change()
            self._append(
                LearningEvent(
                    timestamp=self._rel_ts(),
                    event_type="scroll",
                    x=float(x),
                    y=float(y),
                    window_title=title,
                    process_name=proc,
                    metadata={"dx": int(dx), "dy": int(dy)},
                )
            )

        def on_press(key):
            if not self._hooks_active or not self._record_keyboard:
                return
            self._handle_key("key_down", _key_name(key))

        def on_release(key):
            if not self._hooks_active or not self._record_keyboard:
                return
            self._handle_key("key_up", _key_name(key))

        self._mouse_listener = mouse.Listener(
            on_move=on_move, on_click=on_click, on_scroll=on_scroll
        )
        self._keyboard_listener = keyboard.Listener(
            on_press=on_press, on_release=on_release
        )
        self._hooks_active = True
        self._hook_backend = "pynput"
        self._mouse_listener.start()
        self._keyboard_listener.start()

    def _handle_mouse_button(self, x: float, y: float, btn: str, pressed: bool) -> None:
        proc, title = self._maybe_window_change()
        if pressed:
            if btn == "left":
                self._drag_active = True
                self._drag_path = [(x, y)]
            et = "right_click" if btn == "right" else "press"
            if btn == "left":
                et = "press"
            self._append(
                LearningEvent(
                    timestamp=self._rel_ts(),
                    event_type=et,
                    x=x,
                    y=y,
                    window_title=title,
                    process_name=proc,
                    metadata={"button": btn, "pressed": True},
                )
            )
            return
        if btn == "left" and self._drag_active:
            path = list(self._drag_path)
            self._drag_active = False
            self._drag_path = []
            if len(path) >= 2:
                dx = abs(path[-1][0] - path[0][0])
                dy = abs(path[-1][1] - path[0][1])
                if dx + dy > 8:
                    self._append(
                        LearningEvent(
                            timestamp=self._rel_ts(),
                            event_type="drag",
                            x=path[-1][0],
                            y=path[-1][1],
                            window_title=title,
                            process_name=proc,
                            metadata={
                                "path": path[:: max(1, len(path) // 20)],
                                "start": path[0],
                                "end": path[-1],
                            },
                        )
                    )
                    return
            self._append(
                LearningEvent(
                    timestamp=self._rel_ts(),
                    event_type="click",
                    x=x,
                    y=y,
                    window_title=title,
                    process_name=proc,
                    metadata={"button": "left"},
                )
            )
            return
        self._append(
            LearningEvent(
                timestamp=self._rel_ts(),
                event_type="release",
                x=x,
                y=y,
                window_title=title,
                process_name=proc,
                metadata={"button": btn, "pressed": False},
            )
        )

    def _handle_key(self, event_type: str, name: str | None) -> None:
        proc, title = self._maybe_window_change()
        pwd = _is_password_control()
        key = name
        if not self._store_key_chars and key and len(key) == 1:
            key = "*"
        key = redact_key_if_needed(
            key, window_title=title, process_name=proc, is_password_control=pwd
        )
        self._append(
            LearningEvent(
                timestamp=self._rel_ts(),
                event_type=event_type,
                key=key,
                window_title=title,
                process_name=proc,
                metadata={"password": pwd},
            )
        )

    def _start_win32_hooks(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            from iris.learning.win32_hooks import Win32InputHooks
        except Exception as exc:
            log.warning("win32 hooks import failed: %s", exc)
            return False

        def on_mouse(kind: str, x: float, y: float, meta: dict) -> None:
            if not self._hooks_active:
                return
            if kind == "move":
                if self._drag_active:
                    self._drag_path.append((x, y))
                return
            if kind == "scroll":
                proc, title = self._maybe_window_change()
                self._append(
                    LearningEvent(
                        timestamp=self._rel_ts(),
                        event_type="scroll",
                        x=x,
                        y=y,
                        window_title=title,
                        process_name=proc,
                        metadata=meta,
                    )
                )
                return
            if kind == "press":
                self._handle_mouse_button(x, y, str(meta.get("button") or "left"), True)
            elif kind == "release":
                self._handle_mouse_button(x, y, str(meta.get("button") or "left"), False)

        def on_key(kind: str, name: str, meta: dict) -> None:
            if not self._hooks_active or not self._record_keyboard:
                return
            self._handle_key(kind, name)

        hooks = Win32InputHooks(on_mouse=on_mouse, on_key=on_key)
        hooks.start()
        self._win32_hooks = hooks
        self._hooks_active = True
        self._hook_backend = "win32"
        log.info("using Win32 low-level hooks")
        return True

    def _stop_hooks(self) -> None:
        self._hooks_active = False
        for listener in (self._mouse_listener, self._keyboard_listener):
            if listener is None:
                continue
            try:
                listener.stop()
            except Exception:
                pass
        self._mouse_listener = None
        self._keyboard_listener = None
        win32 = getattr(self, "_win32_hooks", None)
        if win32 is not None:
            try:
                win32.stop()
            except Exception:
                pass
            self._win32_hooks = None

    def _start_video(self) -> None:
        out = self._dir / "inputs" / "recording.mp4"
        fps = self.fps
        running = lambda: self._running

        def _loop() -> None:
            try:
                import mss
                import numpy as np

                try:
                    import cv2
                except ImportError:
                    log.warning("opencv 없음 — 프레임 PNG 시퀀스로 저장")
                    self._record_png_sequence(out.parent / "frames")
                    return

                with mss.mss() as sct:
                    mon = sct.monitors[1]
                    w, h = mon["width"], mon["height"]
                    # ponytail: mp4v는 호환성 우선; ffmpeg 없으면 여기까지
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(str(out), fourcc, fps, (w, h))
                    if not writer.isOpened():
                        raise RuntimeError("VideoWriter open failed")
                    interval = 1.0 / fps
                    while running():
                        t = time.time()
                        shot = sct.grab(mon)
                        frame = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(
                            (shot.height, shot.width, 4)
                        )
                        bgr = frame[:, :, :3].copy()
                        writer.write(bgr)
                        elapsed = time.time() - t
                        time.sleep(max(0.0, interval - elapsed))
                    writer.release()
            except Exception as exc:
                log.exception("screen capture failed")
                if self._on_error:
                    self._on_error(f"screen capture: {exc}")

        self._video_thread = threading.Thread(
            target=_loop, name=f"iris-learn-video-{self.session_id[:8]}", daemon=True
        )
        self._video_thread.start()

    def _record_png_sequence(self, frames_dir: Path) -> None:
        frames_dir.mkdir(parents=True, exist_ok=True)
        try:
            import mss
            from PIL import Image

            interval = 1.0 / self.fps
            i = 0
            with mss.mss() as sct:
                mon = sct.monitors[1]
                while self._running:
                    t = time.time()
                    shot = sct.grab(mon)
                    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    img.save(frames_dir / f"frame_{i:06d}.png")
                    i += 1
                    time.sleep(max(0.0, interval - (time.time() - t)))
        except Exception as exc:
            log.exception("png sequence failed: %s", exc)


def _key_name(key: object) -> str:
    try:
        from pynput.keyboard import Key

        if isinstance(key, Key):
            return key.name.upper() if key.name else str(key)
        ch = getattr(key, "char", None)
        if ch:
            return ch.upper() if len(ch) == 1 else ch
    except Exception:
        pass
    return str(key).replace("'", "")
