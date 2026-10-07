"""배운 스킬을 화면에서 다시 해 본다 — 로컬에서만, 마우스·키보드를 실제로 움직인다.

클릭할 곳 찾기 (순서대로):
1) 녹화 때 그 클릭 주변 그림을 지금 화면에서 찾는다 (cv2.matchTemplate). 같은 PC 에서
   같은 앱이면 창을 옮겨도 정확하고 즉시 끝난다.
2) 못 찾았거나 바꿔 넣은 값({recipient} 등)이 들어간 대상이면, 화면을 보는 로컬 모델에
   "'{설명}'이 어디 있는지" 물어 위치를 받는다.

안전장치: 실행 중 사용자가 마우스를 움직이거나 Esc 를 누르면 그 자리에서 멈춘다.
글자는 클립보드 붙여넣기로 넣는다 — 한글 IME 상태와 상관없이 그대로 들어간다.
"""

from __future__ import annotations

import io
import json
import logging
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from iris.infrastructure.local_vision import vision_chat
from iris.learning.models import WorkflowRun
from iris.learning.skill import Skill, SkillStep, fill, placeholders
from iris.learning.workflow_registry import LearnedWorkflowRepository

log = logging.getLogger("iris.learning.local_executor")

_MATCH_MIN = 0.86  # 이보다 낮으면 같은 그림으로 보지 않는다
_PATCH_SIZES = ((220, 120), (140, 80))  # 클릭 주변 그림 (원본 픽셀)
_USER_MOVE_PX = 25  # 실행 중 이만큼 마우스가 딴 데로 가 있으면 사람이 끼어든 것
_GROUND_MAX_W = 1280


class ExecutionAborted(RuntimeError):
    pass


@dataclass
class Located:
    x: float
    y: float
    how: str  # template | vision | recorded
    score: float = 0.0


# ----------------------------------------------------------------------
# 화면
# ----------------------------------------------------------------------


def grab_screen():
    """주 모니터 전체 (BGR ndarray, 물리 픽셀)."""
    import mss
    import numpy as np

    with mss.mss() as sct:
        mon = sct.monitors[1]
        shot = sct.grab(mon)
        frame = np.frombuffer(shot.bgra, dtype=np.uint8).reshape((shot.height, shot.width, 4))
        return frame[:, :, :3].copy()


def _small_gray(frame):
    import cv2

    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (g.shape[1] // 8, g.shape[0] // 8), interpolation=cv2.INTER_AREA)


def wait_until_settled(min_sec: float = 0.35, max_sec: float = 3.0) -> None:
    """화면이 그만 바뀔 때까지 — 창이 뜨거나 목록이 그려지는 동안 다음 클릭을 미룬다."""
    import numpy as np

    time.sleep(min_sec)
    end = time.time() + max_sec
    prev = _small_gray(grab_screen())
    while time.time() < end:
        time.sleep(0.25)
        cur = _small_gray(grab_screen())
        if float(np.mean(np.abs(cur.astype(np.int16) - prev.astype(np.int16)))) < 0.6:
            return
        prev = cur


def find_by_template(screen, shot, x: float, y: float) -> Optional[Located]:
    """녹화 화면(shot)의 클릭 주변 그림을 지금 화면에서 찾는다."""
    import cv2

    h, w = shot.shape[:2]
    sg = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    best: Optional[Located] = None
    for pw, ph in _PATCH_SIZES:
        left = int(min(max(0, x - pw / 2), w - pw))
        top = int(min(max(0, y - ph / 2), h - ph))
        patch = cv2.cvtColor(shot[top : top + ph, left : left + pw], cv2.COLOR_BGR2GRAY)
        if patch.size == 0 or float(patch.std()) < 4.0:
            continue  # 단색 배경뿐인 그림은 어디서나 맞는다
        res = cv2.matchTemplate(sg, patch, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score < _MATCH_MIN:
            continue
        # 같은 그림이 여러 군데면(목록의 똑같은 버튼들) 녹화 위치에서 가까운 쪽
        ys, xs = (res >= score - 0.02).nonzero()
        if len(xs) > 1:
            cands = list(zip(xs.tolist(), ys.tolist()))
            loc = min(cands, key=lambda p: (p[0] - left) ** 2 + (p[1] - top) ** 2)
        cx = loc[0] + (x - left)
        cy = loc[1] + (y - top)
        if best is None or score > best.score:
            best = Located(cx, cy, "template", float(score))
        if score >= 0.95:
            break
    return best


def parse_bbox(text: str) -> Optional[tuple[float, float, float, float]]:
    m = re.search(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]", text or "")
    if not m:
        return None
    x1, y1, x2, y2 = (float(v) for v in m.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def find_by_vision(client, model: str, screen, target: str) -> Optional[Located]:
    """화면을 보는 모델에 위치를 묻는다 (qwen2.5vl 은 그림 픽셀 좌표로 답한다)."""
    import cv2

    h, w = screen.shape[:2]
    scale = min(1.0, _GROUND_MAX_W / float(w))
    small = cv2.resize(screen, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", small)
    if not ok:
        return None
    prompt = (
        f'Locate the UI element: "{target}". '
        'Return JSON only: {"bbox_2d": [x1, y1, x2, y2]} in pixel coordinates of this image.'
    )
    try:
        text = vision_chat(client, model, prompt, [buf.tobytes()], timeout_sec=180)
    except Exception as e:
        log.warning("vision locate failed: %s", e)
        return None
    box = parse_bbox(text)
    if box is None:
        return None
    x1, y1, x2, y2 = box
    return Located((x1 + x2) / 2 / scale, (y1 + y2) / 2 / scale, "vision")


def _norm(text: str) -> str:
    return re.sub(r"[\s'\"`()\[\]{}.,:;!?·-]+", "", (text or "").lower())


def text_matches(expected: str, seen: str) -> bool:
    a, b = _norm(expected), _norm(seen)
    return bool(a) and bool(b) and (a in b or b in a)


def verify_spot(client, model: str, screen, x: float, y: float, expected_text: str) -> bool:
    """찾은 자리를 다시 잘라 보고 적힌 글자가 기대한 글자인지 확인한다.

    위치 찾기만 믿으면 '최지호'를 찾으라는데 목록의 '박지원'을 누른다 (실제 사례)."""
    if not expected_text.strip():
        return True
    import cv2
    from PIL import Image

    from iris.learning.local_learner import _DESCRIBE_PROMPT, _CROP, _SEND_SIDE, _draw_pointer, parse_description

    h, w = screen.shape[:2]
    half = _CROP // 2
    left = int(min(max(0, x - half), max(0, w - _CROP)))
    top = int(min(max(0, y - half), max(0, h - _CROP)))
    crop = Image.fromarray(cv2.cvtColor(screen[top : top + _CROP, left : left + _CROP], cv2.COLOR_BGR2RGB))
    _draw_pointer(crop, x - left, y - top)
    crop = crop.resize((_SEND_SIDE, _SEND_SIDE))
    buf = io.BytesIO()
    crop.save(buf, "PNG")
    try:
        text = vision_chat(client, model, _DESCRIBE_PROMPT.format(app="?"), [buf.getvalue()], timeout_sec=180)
    except Exception:
        return False
    target, visible = parse_description(text)
    ok = text_matches(expected_text, visible) or text_matches(expected_text, target)
    log.info("verify %r at %.0f,%.0f -> %r / %r: %s", expected_text, x, y, target, visible, ok)
    return ok


# ----------------------------------------------------------------------
# 입력
# ----------------------------------------------------------------------

_KEYMAP = {
    "enter": "enter", "tab": "tab", "esc": "esc", "backspace": "backspace", "space": "space",
    "delete": "delete", "home": "home", "end": "end", "pageup": "page_up", "pagedown": "page_down",
    "left": "left", "right": "right", "up": "up", "down": "down",
    "ctrl": "ctrl", "shift": "shift", "alt": "alt", "win": "cmd",
}


def _pynput_key(name: str):
    from pynput.keyboard import Key, KeyCode

    n = name.strip().lower()
    if n in _KEYMAP:
        return getattr(Key, _KEYMAP[n])
    if re.fullmatch(r"f\d{1,2}", n):
        return getattr(Key, n)
    if len(n) == 1:
        return KeyCode.from_char(n)
    # 녹화기가 이름을 모르는 키(CapsLock·Insert·한자 등)는 'vk14' 처럼 남긴다
    m = re.fullmatch(r"vk([0-9a-f]{1,2})", n)
    if m:
        return KeyCode.from_vk(int(m.group(1), 16))
    raise ValueError(f"모르는 키: {name}")


def press_hotkey(keys: str) -> None:
    from pynput.keyboard import Controller

    kb = Controller()
    parts = [_pynput_key(k) for k in keys.split("+") if k.strip()]
    for k in parts:
        kb.press(k)
    for k in reversed(parts):
        kb.release(k)


def _set_clipboard(text: str) -> Optional[str]:
    import win32clipboard
    import win32con

    old: Optional[str] = None
    win32clipboard.OpenClipboard()
    try:
        try:
            old = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        except Exception:
            old = None
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()
    return old


def type_text(text: str, *, clear_first: bool) -> None:
    if clear_first:
        press_hotkey("ctrl+a")
        time.sleep(0.05)
    old = _set_clipboard(text)
    time.sleep(0.05)
    press_hotkey("ctrl+v")
    time.sleep(0.25)
    if old is not None:
        try:
            _set_clipboard(old)
        except Exception:
            pass


# ----------------------------------------------------------------------
# 창
# ----------------------------------------------------------------------


def _process_windows(process: str) -> list[tuple[int, str]]:
    """(hwnd, title) — 그 실행 파일이 띄운 보이는 최상위 창."""
    import ctypes
    from ctypes import wintypes

    import psutil

    user32 = ctypes.windll.user32
    out: list[tuple[int, str]] = []
    want = process.lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # GW_OWNER
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            name = psutil.Process(int(pid.value)).name().lower()
        except Exception:
            return True
        if name == want:
            out.append((int(hwnd), buf.value or ""))
        return True

    user32.EnumWindows(cb, 0)
    return out


def process_at(x: float, y: float) -> str:
    """그 점에 보이는 창의 실행 파일 이름."""
    import ctypes
    from ctypes import wintypes

    import psutil

    user32 = ctypes.windll.user32
    hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        return psutil.Process(int(pid.value)).name()
    except Exception:
        return ""


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    import ctypes
    from ctypes import wintypes

    r = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def find_by_window_offset(step: SkillStep) -> Optional[Located]:
    """녹화 때 그 창 안에서 누른 자리를 지금 그 창에서 다시 계산한다.

    입력창은 글자가 들어 있으면 녹화 때 그림(안내 문구)과 달라 그림 맞추기가 실패한다.
    창 모양이 같은 앱이라면 창 안 위치는 그대로다."""
    if len(step.win_rect) != 4 or not step.title:
        return None
    wins = [h for h, t in _process_windows(step.process) if t == step.title]
    if not wins:
        return None
    l0, t0, r0, b0 = step.win_rect
    l1, t1, r1, b1 = window_rect(wins[0])
    w0, h0, w1, h1 = r0 - l0, b0 - t0, r1 - l1, b1 - t1
    if w0 <= 0 or h0 <= 0 or w1 <= 0 or h1 <= 0:
        return None
    # 크기가 바뀌었으면 비율로 — 입력창·버튼은 보통 창 아래·오른쪽에 붙어 있어 가장자리 기준이 더 맞는다
    fx, fy = (step.x - l0) / w0, (step.y - t0) / h0
    x = l1 + (step.x - l0) if fx < 0.5 else r1 - (r0 - step.x)
    y = t1 + (step.y - t0) if fy < 0.5 else b1 - (b0 - step.y)
    if not (l1 <= x < r1 and t1 <= y < b1):
        return None
    return Located(float(x), float(y), "window_offset")


def focus_window(hwnd: int) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # 다른 앱이 앞에 있으면 SetForegroundWindow 가 거절된다 — Alt 를 한 번 눌렀다 떼면 풀린다
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)


def ensure_app(step: SkillStep, timeout_sec: float = 20.0) -> None:
    wins = _process_windows(step.process)
    if not wins and step.exe and Path(step.exe).is_file():
        subprocess.Popen([step.exe], close_fds=True)
        end = time.time() + timeout_sec
        while time.time() < end and not wins:
            time.sleep(0.5)
            wins = _process_windows(step.process)
    if not wins:
        raise RuntimeError(f"{step.process} 창을 찾지 못했어요 (앱이 꺼져 있나요?)")
    # 녹화 때 그 제목의 창이 있으면 그 창, 아니면 첫 창
    hwnd = next((h for h, t in wins if t == step.title), wins[0][0])
    focus_window(hwnd)


def wait_for_window(process: str, title: str, timeout_sec: float = 4.0) -> None:
    """녹화 때 클릭한 창(예: 방금 연 대화방)이 뜰 때까지 잠깐 기다렸다가 앞으로."""
    if not process or not title:
        return
    end = time.time() + timeout_sec
    while True:
        for hwnd, t in _process_windows(process):
            if t == title:
                focus_window(hwnd)
                return
        if time.time() >= end:
            return
        time.sleep(0.25)


# ----------------------------------------------------------------------
# 실행기
# ----------------------------------------------------------------------


class _Watchdog:
    """사람이 끼어들면(마우스 이동·Esc) 멈춘다."""

    def __init__(self) -> None:
        self.aborted = ""
        self.expected: Optional[tuple[float, float]] = None
        self._kb = None

    def start(self) -> None:
        from pynput import keyboard

        def on_press(key, injected=False):
            # injected = 우리가 SendInput 으로 누른 키 — 녹화된 Esc 를 재생할 때 멈추면 안 된다
            if key == keyboard.Key.esc and not injected:
                self.aborted = "Esc 를 눌러 멈췄어요"

        self._kb = keyboard.Listener(on_press=on_press)
        self._kb.start()

    def stop(self) -> None:
        if self._kb is not None:
            self._kb.stop()

    def check(self) -> None:
        if not self.aborted and self.expected is not None:
            from pynput.mouse import Controller

            x, y = Controller().position
            ex, ey = self.expected
            if abs(x - ex) > _USER_MOVE_PX or abs(y - ey) > _USER_MOVE_PX:
                self.aborted = "마우스를 움직여서 멈췄어요"
        if self.aborted:
            raise ExecutionAborted(self.aborted)


class LocalSkillExecutor:
    """ExecutorProtocol 구현. execute() 는 바로 돌아오고 실제 조작은 뒤 스레드에서 한다."""

    def __init__(
        self,
        registry: LearnedWorkflowRepository,
        *,
        ollama_base_url: str = "http://127.0.0.1:11434/v1",
        model_provider: Callable[[], Optional[str]] | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self._registry = registry
        self._base_url = ollama_base_url
        self._model_provider = model_provider
        self._on_progress = on_progress
        self._runs: dict[str, WorkflowRun] = {}
        self._lock = threading.Lock()
        self._active: Optional[str] = None

    def _progress(self, msg: str) -> None:
        log.info(msg)
        if self._on_progress:
            try:
                self._on_progress(msg)
            except Exception:
                pass

    # --- ExecutorProtocol ---
    def execute(
        self,
        *,
        trace_id: str,
        task: str,
        workflow_id: int = 0,
        params: Optional[dict[str, str]] = None,
        skill_path: str = "",
        wait: bool = False,
    ) -> WorkflowRun:
        run = WorkflowRun(
            run_id=uuid.uuid4().hex,
            workflow_id=workflow_id,
            trace_id=trace_id,
            task=task,
            status="running",
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        if not skill_path:
            # 예전 클라우드 방식(ShowUI-Aloha)으로 배운 업무 — 스킬 파일이 없어 이 실행기로는 못 돈다
            run.status = "failed"
            run.message = "예전 방식으로 배운 업무라 실행할 수 없어요. 한 번 더 보여 주시면 다시 배울게요."
            run.finished_at = run.started_at
            return run
        with self._lock:
            if self._active is not None:
                run.status = "failed"
                run.message = "다른 업무를 실행하는 중이에요"
                run.finished_at = run.started_at
                return run
            self._active = run.run_id
        self._runs[run.run_id] = run
        self._save(run)
        t = threading.Thread(
            target=self._run, args=(run, skill_path, dict(params or {})), daemon=True,
            name="iris-skill-run",
        )
        t.start()
        if wait:
            t.join()
        return run

    def get_status(self, run_id: str) -> WorkflowRun | None:
        return self._runs.get(run_id)

    def shutdown(self) -> None:
        return None

    # --- 실행 ---
    def _save(self, run: WorkflowRun) -> None:
        try:
            self._registry.save_run(
                run_id=run.run_id, workflow_id=run.workflow_id, trace_id=run.trace_id,
                task=run.task, status=run.status, message=run.message,
                started_at=run.started_at, finished_at=run.finished_at,
            )
        except Exception:
            log.exception("save run")

    def _run(self, run: WorkflowRun, skill_path: str, params: dict[str, str]) -> None:
        watchdog = _Watchdog()
        try:
            skill = Skill.load(Path(skill_path))
            missing = sorted({n for s in skill.steps for n in placeholders(s.text + s.target)} - set(params))
            if missing:
                # 값을 안 주면 녹화 때 값으로 — "그대로 한 번 더" 요청
                for p in skill.params:
                    params.setdefault(p.name, p.example)
            watchdog.start()
            self._run_steps(skill, params, watchdog, run)
            run.status = "succeeded"
            run.message = f"{len(skill.steps)}단계 완료"
            if run.workflow_id:
                self._registry.mark_run(run.workflow_id)
        except ExecutionAborted as e:
            run.status = "cancelled"
            run.message = str(e)
        except Exception as e:
            log.exception("skill run failed")
            run.status = "failed"
            run.message = str(e)[:400]
        finally:
            watchdog.stop()
            run.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._save(run)
            with self._lock:
                self._active = None
            self._progress(f"업무 실행 {'완료' if run.status == 'succeeded' else '중단'}: {run.message}")

    def _save_failure_shot(self, session: Path, run: WorkflowRun, step_no: int) -> None:
        """막힌 순간의 화면 — 왜 못 찾았는지 나중에 볼 수 있게 세션 폴더에 남긴다."""
        try:
            import cv2

            out = session / "runs" / f"{run.run_id[:8]}_step{step_no}.jpg"
            out.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out), grab_screen(), [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        except Exception:
            log.exception("failure screenshot")

    def _vision(self):
        from iris.infrastructure.ollama_client import OllamaClient

        client = OllamaClient(self._base_url)
        model = self._model_provider() if self._model_provider else None
        return client, model

    def _locate(
        self,
        step: SkillStep,
        params: dict[str, str],
        session: Path,
        wd: _Watchdog,
        mouse,
        *,
        before_typing: bool = False,
    ) -> Optional[Located]:
        import cv2


        dynamic = bool(placeholders(step.target) or placeholders(step.visible_text))
        shot = None
        if not dynamic and step.shot and (session / step.shot).is_file():
            shot = cv2.imread(str(session / step.shot))
        screen = grab_screen()
        if shot is not None:
            spot = find_by_template(screen, shot, step.x, step.y)
            if spot is not None:
                return spot
            # 녹화 때와 달리 목록이 스크롤돼 있으면 못 찾는다 — 그 창을 맨 위로 올려 다시 본다
            if process_at(step.x, step.y).lower() == step.process.lower():
                mouse.position = (int(step.x), int(step.y))
                wd.expected = (int(step.x), int(step.y))
                mouse.scroll(0, 25)
                wait_until_settled()
                wd.check()
                screen = grab_screen()
                spot = find_by_template(screen, shot, step.x, step.y)
                if spot is not None:
                    return spot
        if before_typing:
            # 글자를 넣기 직전의 클릭은 입력창이다 — 창 안 같은 자리
            spot = find_by_window_offset(step)
            if spot is not None and process_at(spot.x, spot.y).lower() == step.process.lower():
                return spot
        if not step.target:
            return None
        client, model = self._vision()
        if not model:
            return None
        target = fill(step.target, params)
        expected = fill(step.visible_text, params)
        if expected and expected not in target:
            target = f"{target} ('{expected}')"
        spot = find_by_vision(client, model, screen, target)
        if spot is None:
            return None
        # 3B 모델은 없는 요소도 그럴듯한 좌표로 답한다 — 그 앱의 창 안이고, 그 자리에
        # 기대한 글자가 적혀 있을 때만 누른다
        if step.process and process_at(spot.x, spot.y).lower() != step.process.lower():
            log.warning("vision spot outside %s — ignored", step.process)
            return None
        if not verify_spot(client, model, screen, spot.x, spot.y, expected):
            log.warning("vision spot text mismatch for %r — ignored", expected)
            return None
        return spot

    def _run_steps(self, skill: Skill, params: dict[str, str], wd: _Watchdog, run: WorkflowRun) -> None:
        from pynput.mouse import Button, Controller


        mouse = Controller()
        session = Path(skill.session_dir)
        total = len(skill.steps)
        for i, step in enumerate(skill.steps, 1):
            wd.check()
            label = step.target or step.text or step.keys or step.process
            self._progress(f"업무 실행 {i}/{total}: {step.kind} {fill(label, params)[:40]}")
            run.message = f"{i}/{total} 단계"
            if step.kind == "activate_app":
                ensure_app(step)
            elif step.kind == "click":
                wait_for_window(step.process, step.title)
                nxt = skill.steps[i] if i < total else None
                spot = self._locate(
                    step, params, session, wd, mouse,
                    before_typing=nxt is not None and nxt.kind == "type" and nxt.process == step.process,
                )
                if spot is None:
                    self._save_failure_shot(session, run, i)
                    raise RuntimeError(f"{i}단계: '{fill(label, params)}'을(를) 화면에서 찾지 못했어요")
                log.info("step %d click via %s (%.2f) at %.0f,%.0f", i, spot.how, spot.score, spot.x, spot.y)
                mouse.position = (int(spot.x), int(spot.y))
                time.sleep(0.08)
                button = Button.right if step.button == "right" else Button.left
                mouse.click(button, 2 if step.double else 1)
                wd.expected = (int(spot.x), int(spot.y))
            elif step.kind == "type":
                type_text(fill(step.text, params), clear_first=step.clear_first)
            elif step.kind == "hotkey":
                press_hotkey(step.keys)
            elif step.kind == "scroll":
                mouse.position = (int(step.x), int(step.y))
                wd.expected = (int(step.x), int(step.y))
                mouse.scroll(0, step.dy)
            wait_until_settled()
            wd.check()
