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
    looks_like_credential_window,
    redact_key_if_needed,
    redact_text_if_needed,
)
from iris.learning.typing_capture import (
    MODIFIER_VKS,
    VK_BACK,
    VK_HANGUL,
    VK_RMENU,
    TypingBuffer,
    control_class,
    focused_control,
    ime_hangul_mode,
    read_control_text,
    vk_key_name,
    vk_to_char,
)

log = logging.getLogger("iris.learning.recorder")


def _process_exe(hwnd: int) -> str:
    """창을 띄운 실행 파일 경로 — 실행할 때 그 앱이 꺼져 있으면 이걸로 켠다."""
    try:
        import ctypes
        from ctypes import wintypes

        import psutil

        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return psutil.Process(int(pid.value)).exe()
    except Exception:
        return ""


def _window_under(x: float, y: float) -> dict[str, str]:
    """클릭 지점의 최상위 창 — 포커스 창이 아니라 실제로 누른 창 (작업 표시줄 구분용)."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
        root = user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(root, cls, 128)
        n = user32.GetWindowTextLengthW(root)
        title = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(root, title, n + 1)
        rect = wintypes.RECT()
        user32.GetWindowRect(root, ctypes.byref(rect))
        return {
            "class": cls.value or "",
            "title": title.value or "",
            # 창 안에서 어디를 눌렀는지 — 입력창처럼 그림이 바뀌는 곳을 다시 누를 때 쓴다
            "rect": [rect.left, rect.top, rect.right, rect.bottom],
        }
    except Exception:
        return {}


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

            # 포커스가 잠깐 비면 pid 0 → 'System Idle Process'. 앱이 아니다 (실제 사례)
            if int(pid.value) > 0:
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
        # 입력 글자 복원 — 눌린 수식키(vk)와 지금 이어지는 입력
        self._mods: set[int] = set()
        self._ralt_solo = False
        self._typing = TypingBuffer()
        # 이번 입력 묶음 중 비밀번호 칸에서 친 글자가 있었나 — 정리 시점(창 전환 뒤)의
        # 포커스로 판단하면 Alt+Tab 하는 순간 비밀번호가 평문으로 남는다
        self._typing_sensitive = False
        # 클릭 순간 화면 — 영상 스레드가 계속 갈아 끼우는 최신 프레임
        self._latest_frame = None
        self._shot_seq = 0
        self._pending_shot = ""
        self._pending_under: dict[str, str] = {}
        self._shot_threads: list[threading.Thread] = []
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
        self._flush_typing("stop")

    def finalize(self, *, status: str = "finalized") -> SessionManifest:
        self._running = False
        self._stop_hooks()
        self._flush_typing("stop")
        if self._video_thread and self._video_thread.is_alive():
            self._video_thread.join(timeout=5.0)
        for t in self._shot_threads:
            t.join(timeout=5.0)
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
            self._flush_typing("window_change")
            self._append(
                LearningEvent(
                    timestamp=self._rel_ts(),
                    event_type="window_change",
                    window_title=title,
                    process_name=proc,
                    metadata={
                        "hwnd": hwnd,
                        "exe": _process_exe(hwnd),
                        "prev": {"process": prev[0], "title": prev[1]},
                    },
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
            self._handle_key("key_down", _key_name(key), _key_vk(key))

        def on_release(key):
            if not self._hooks_active or not self._record_keyboard:
                return
            self._handle_key("key_up", _key_name(key), _key_vk(key))

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
            self._flush_typing("click")
            # 누르기 직전 화면 — 무엇을 눌렀는지 학습할 때 쓴다
            self._pending_shot = self._save_click_shot()
            self._pending_under = _window_under(x, y)
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
                    metadata={
                        "button": btn,
                        "pressed": True,
                        "shot": self._pending_shot,
                        "under": self._pending_under,
                    },
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
                    metadata={"button": "left", "shot": self._pending_shot, "under": self._pending_under},
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

    def _handle_key(self, event_type: str, name: str | None, vk: int = 0) -> None:
        proc, title = self._maybe_window_change()
        pwd = _is_password_control()
        key = name
        if not self._store_key_chars and key and len(key) == 1:
            key = "*"
        key = redact_key_if_needed(
            key, window_title=title, process_name=proc, is_password_control=pwd
        )
        # 글자를 가렸으면 가상 키 코드도 남기지 않는다 (0x41~0x5A 가 곧 글자)
        masked = key != name
        self._append(
            LearningEvent(
                timestamp=self._rel_ts(),
                event_type=event_type,
                key=key,
                window_title=title,
                process_name=proc,
                metadata={"password": pwd, "vk": 0 if masked else vk},
            )
        )
        if vk:
            self._track_typing(event_type, vk, proc, title, pwd)

    # ------------------------------------------------------------------
    # 입력 글자 복원 (typing_capture) — type_text / hotkey 이벤트를 만든다
    # ------------------------------------------------------------------

    def _track_typing(self, event_type: str, vk: int, proc: str, title: str, pwd: bool) -> None:
        if vk in MODIFIER_VKS:
            if event_type == "key_down":
                if vk == VK_RMENU and vk not in self._mods:
                    self._ralt_solo = True
                self._mods.add(vk)
            else:
                self._mods.discard(vk)
                if vk == VK_RMENU and self._ralt_solo and self._typing.started:
                    self._typing.toggle_hangul()  # 오른쪽 Alt 만 눌렀다 뗌 = 한/영
                self._ralt_solo = False
            return
        if event_type == "key_down":
            self._ralt_solo = False
        if event_type != "key_down":
            return
        if vk == VK_HANGUL:
            if self._typing.started:
                self._typing.toggle_hangul()
            return
        shift = bool(self._mods & {0x10, 0xA0, 0xA1})
        combo = [m for m, vks in (("ctrl", {0x11, 0xA2, 0xA3}), ("alt", {0x12, 0xA4, 0xA5}),
                                  ("win", {0x5B, 0x5C})) if self._mods & vks]
        ch = None if combo else vk_to_char(vk, shift)
        if ch is not None:
            if not self._typing.started:
                fg = self._last_fg[2]
                self._typing.started = True
                self._typing.hangul = ime_hangul_mode(fg)
                self._typing.focus_hwnd = focused_control(fg)
            if pwd or looks_like_credential_window(title, proc):
                self._typing_sensitive = True
            self._typing.add(ch)
            return
        if vk == VK_BACK and self._typing.started:
            self._typing.backspace()
            return
        # 글자가 아닌 키(Enter·Tab·Ctrl+F 등) — 지금까지 친 글자를 먼저 정리하고 키를 남긴다
        self._flush_typing("key")
        if shift:
            # Shift+Enter(카톡 줄바꿈)·Shift+Tab 도 Shift 를 빼면 다른 동작이 된다
            combo.insert(1 if "ctrl" in combo else 0, "shift")
        name = "+".join([*combo, vk_key_name(vk)])
        self._append(
            LearningEvent(
                timestamp=self._rel_ts(),
                event_type="hotkey",
                key=name,
                window_title=title,
                process_name=proc,
                metadata={"vk": vk},
            )
        )

    def _flush_typing(self, reason: str) -> None:
        buf = self._typing
        if not buf.started:
            return
        proc, title, fg = self._last_fg
        focus = buf.focus_hwnd or focused_control(fg)
        sensitive = (
            self._typing_sensitive
            or _is_password_control()
            or looks_like_credential_window(title, proc)
        )
        self._typing_sensitive = False
        # 글자 저장을 끈 정책이면 화면 글자·키 기록도 남기지 않는다
        keep = not sensitive and self._store_key_chars
        control_text = read_control_text(focus) if keep else None
        raw_keys, hangul_mode = buf.raw(), buf.hangul
        typed = buf.resolve(control_text, control_class(focus))
        buf.reset()
        if typed is None:
            return
        text = "[REDACTED]" if sensitive or not self._store_key_chars else typed.text
        self._append(
            LearningEvent(
                timestamp=self._rel_ts(),
                event_type="type_text",
                text=text,
                window_title=title,
                process_name=proc,
                metadata={
                    "source": typed.source,
                    "focus_class": typed.focus_class,
                    "field_text": typed.field_text if keep else "",
                    "ended_by": reason,
                    "sensitive": sensitive,
                    # 글자 복원이 틀렸을 때 원인을 보려고 — 비밀번호 창이면 남기지 않는다
                    "raw_keys": raw_keys if keep else "",
                    "ime_hangul": hangul_mode,
                },
            )
        )

    def _save_click_shot(self) -> str:
        """영상 스레드의 최신 프레임을 JPEG 로 — 인코딩은 훅 스레드 밖에서."""
        frame = self._latest_frame
        if frame is None:
            return ""
        self._shot_seq += 1
        path = self._dir / "screenshots" / f"click_{self._shot_seq:04d}.jpg"

        def write() -> None:
            try:
                import cv2

                path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            except Exception:
                log.exception("click screenshot failed")

        t = threading.Thread(target=write, daemon=True, name="iris-learn-shot")
        t.start()
        self._shot_threads.append(t)
        return str(path.relative_to(self._dir)).replace("\\", "/")

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
            self._handle_key(kind, name, int(meta.get("vk") or 0))

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
                        self._latest_frame = bgr
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


def _key_vk(key: object) -> int:
    """pynput 키의 가상 키 코드 — 글자 복원은 이름이 아니라 vk 로 한다."""
    vk = getattr(key, "vk", None)
    if vk is None:
        value = getattr(key, "value", None)  # Key 열거형 (Key.enter 등)
        vk = getattr(value, "vk", None)
    try:
        return int(vk or 0)
    except (TypeError, ValueError):
        return 0
