"""MainWindow ↔ Control Surface 액션 바인딩.

ponytail: UI 핸들러를 그대로 감싼다. 새 UX 없음.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal

from iris.storage.email_accounts import (
    add_email_account,
    find_account,
    load_email_accounts,
    remove_email_account,
)
from iris.storage.user_profile import UserProfile, load_user_profile, save_user_profile
from iris.system.control_surface import (
    ControlSurface,
    MainThreadInvoker,
    UiThreadTimeout,
    err_result,
    ok_result,
    resolve_control_token,
)
from iris.system.ide_launcher import ide_catalog, is_ide_installed
from iris.learning.permission import policy_for

if TYPE_CHECKING:
    from iris.ui.window.main_window import MainWindow


class _QtInvoker(QObject):
    _call = pyqtSignal(object, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._call.connect(self._on_call, Qt.ConnectionType.QueuedConnection)

    def _on_call(self, fn: object, box: object) -> None:
        assert callable(fn) and isinstance(box, dict)
        try:
            box["value"] = fn()
            box["exc"] = None
        except Exception as exc:  # noqa: BLE001
            box["value"] = None
            box["exc"] = exc
        box["event"].set()

    def run(self, fn: Callable[[], Any], timeout: float = 15.0) -> Any:
        box: dict[str, Any] = {"event": threading.Event()}
        self._call.emit(fn, box)
        if not box["event"].wait(timeout):
            raise UiThreadTimeout()
        if box["exc"] is not None:
            raise box["exc"]
        return box["value"]


def _public_profile(p: UserProfile) -> dict[str, Any]:
    return {
        "name": p.name,
        "occupation": p.occupation,
        "hobbies": p.hobbies,
        "interests": p.interests,
        "work_tasks": p.work_tasks,
        "age": p.age,
        "gender": p.gender,
        "residence": p.residence,
        "contact": p.contact,
        "email": p.email,
        "preferred_ide": p.preferred_ide,
        "ide_exe_path": p.ide_exe_path,
        "ide_cli_path": p.ide_cli_path,
        "project_root": p.project_root,
        "project_parents": list(p.project_parents or []),
    }


def _profile_parents(window: MainWindow) -> list[Path]:
    from iris.system.project_ops import resolve_project_parents

    profile = load_user_profile(window._db)
    return resolve_project_parents(list(profile.project_parents or []))


def _iris_ide_client(window: MainWindow):
    session = window._get_bound_ide_session(refresh=False)
    if session is None or session.ide_id != "iris_ide":
        return None
    try:
        return window._iris_ide_bridge_client()
    except Exception:  # noqa: BLE001
        return None


# 예산·캐시·토큰은 iris.system.ide_link. 이 값은 기존 자검이 상한으로 읽는다.
_IDE_CONTEXT_BUDGET = 1.5


def _iris_ide_context(window: MainWindow) -> dict[str, Any]:
    from iris.system.ide_link import shared_ide_link

    return shared_ide_link().editor_state(_iris_ide_client(window))


def _ide_open_file_path(
    window: MainWindow,
    path: str,
    *,
    line: int = 1,
    column: int = 1,
    reuse_window: bool = True,
) -> dict[str, Any]:
    session = window._get_bound_ide_session(refresh=True)
    if session is None:
        return {
            "ok": False,
            "path": path,
            "error": "bound IDE session required",
            "line": line,
            "column": column,
        }
    if session.ide_id == "iris_ide":
        try:
            from iris.system.ide_link import shared_ide_link
            from iris.system.project_ops import workspace_rel_for_open

            try:
                rel = workspace_rel_for_open(session.workspace_root, path) if session.workspace_root else path
            except ValueError as exc:
                return {
                    "ok": False,
                    "path": path,
                    "error": str(exc),
                    "line": line,
                    "column": column,
                }
            target = Path(session.workspace_root) / rel if session.workspace_root else Path(rel)
            if not target.is_file():
                return {
                    "ok": False,
                    "path": path,
                    "error": f"file not found: {rel}",
                    "line": line,
                    "column": column,
                }
            link = shared_ide_link()
            out = _bridge_call_pumping(lambda: link.open_file(rel, line=line, column=column))
            return {
                "ok": True,
                "path": path,
                "error": None,
                "line": line,
                "column": column,
                "visible": True,
                "bridge": out,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "path": path,
                "error": str(exc),
                "line": line,
                "column": column,
            }
    from iris.automation.ide_input import open_file_in_workspace, wait_ide_shows_file

    if not session.hwnd:
        return {
            "ok": False,
            "path": path,
            "error": "bound IDE session required",
            "line": line,
            "column": column,
        }
    ok = open_file_in_workspace(
        int(session.hwnd),
        path,
        workspace_root=session.workspace_root,
        pump=_qt_pump,
        pid=session.pid,
    )
    visible = False
    if ok:
        visible = wait_ide_shows_file(
            int(session.hwnd),
            path,
            timeout_sec=6.0,
            pump=_qt_pump,
        )
    return {
        "ok": bool(ok),
        "path": path,
        "error": None if ok else "bound IDE session quick open failed",
        "line": line,
        "column": column,
        "visible": visible,
        "hwnd": session.hwnd,
    }


def _bound_session(window: MainWindow, *, require_workspace: bool = False) -> tuple[Any, str]:
    # refresh는 IDE 창 위젯 상태를 읽는다 — 오프-UI 액션에서도 안전하도록 마샬
    session = _call_on_ui(window, lambda: window._get_bound_ide_session(refresh=True))
    if session is None:
        return None, "bound IDE session required"
    if require_workspace and (session.mode != "workspace" or not session.workspace_root):
        return None, "bound IDE workspace session required"
    return session, ""


def _qt_pump() -> None:
    """processEvents는 GUI 스레드 전용 — 오프-UI 액션에서 부르면 no-op."""
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None and app.thread() is QThread.currentThread():
            app.processEvents()
    except Exception:
        pass


class BridgeCallTimeout(Exception):
    """브리지 응답 대기 초과. UI 스레드 대기(UiThreadTimeout)가 아니다."""

    def __init__(self) -> None:
        super().__init__("iris_ide bridge call timeout")


def _bridge_call_pumping(call: Callable[[], Any], *, timeout: float = 20.0) -> Any:
    """프런트엔드 왕복이 필요한 브리지 호출을 UI 스레드를 막지 않고 기다린다.

    IRIS IDE는 같은 프로세스의 QWebEngineView다. UI 스레드에서 응답을 기다리면
    QtWebEngine의 in-process 네트워크 서비스가 멈춰 Theia가 폴링·응답을 못 하고,
    브리지는 3.5초 뒤 bridge_fallback으로 이탈한다 (파일은 나중에야 열린다).
    """
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["value"] = call()
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    deadline = time.monotonic() + timeout
    while worker.is_alive() and time.monotonic() < deadline:
        _qt_pump()
        time.sleep(0.02)
    if "error" in box:
        raise box["error"]
    if "value" not in box:
        raise BridgeCallTimeout()
    return box["value"]


def start_control_surface(window: MainWindow) -> ControlSurface | None:
    """Control Surface 기동 + 액션 등록. 실패 시 None (앱은 계속)."""
    import os

    if getattr(window, "_test_mode", False):
        return None
    if os.environ.get("IRIS_CONTROL_ENABLED", "1").strip() in ("0", "false", "False"):
        return None

    host = (os.environ.get("IRIS_CONTROL_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int((os.environ.get("IRIS_CONTROL_PORT") or "8765").strip() or "8765")
    except ValueError:
        port = 8765
    token = resolve_control_token()

    qt = _QtInvoker(window)
    invoker = MainThreadInvoker()
    invoker.bind(qt.run)
    surface = ControlSurface(invoker=invoker, host=host, port=port, token=token)
    _register_actions(window, surface)
    try:
        bound = surface.start()
    except OSError as exc:
        window._live_activity.append_instant_line(f"Iris control: bind failed ({exc})")
        return None

    # ponytail: sync는 UI 스레드에서 하지 않음 — /v1/state 프로브가 같은 스레드 invoker와
    # 데드락 나며 Windows "응답 없음"이 됨. HermesHealthWorker가 백그라운드에서 동기화.
    window._control_surface = surface  # type: ignore[attr-defined]
    window._control_qt_invoker = qt  # type: ignore[attr-defined]
    window._live_activity.append_instant_line(
        f"Iris control: listening on http://{host}:{bound} (MCP iris-control)"
    )
    return surface


def stop_control_surface(window: MainWindow) -> None:
    surface = getattr(window, "_control_surface", None)
    if surface is not None:
        try:
            surface.stop()
        except Exception:
            pass
        window._control_surface = None  # type: ignore[attr-defined]


def mark_control_ready(window: MainWindow) -> None:
    surface = getattr(window, "_control_surface", None)
    if surface is not None:
        surface.booting = False


def _log(window: MainWindow, action: str, ok: bool) -> None:
    status = "ok" if ok else "fail"
    _append_activity(window, f"Iris control: {action} {status}")


def _first_class_ide_trigger(
    window: MainWindow, action: Callable[[dict[str, Any]], dict[str, Any]]
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """액션 성공을 이번 턴의 IDE 개방 트리거로 확정한다 (연번 11).

    성공 반환 지점이 여러 곳이라 등록 시점에 감싼다.
    """

    def _wrapped(args: dict[str, Any]) -> dict[str, Any]:
        result = action(args)
        if result.get("ok"):
            window._note_tool_file_write()
        return result

    return _wrapped


def _append_activity(window: MainWindow, line: str) -> None:
    def _do() -> None:
        try:
            window._live_activity.append_instant_line(line)
        except Exception:
            pass

    _call_on_ui(window, _do)


def _call_on_ui(window: MainWindow, fn: Callable[[], Any]) -> Any:
    """UI 위젯 접근 마샬. 이미 메인이면 직접 호출 (Queued+wait 데드락 금지)."""
    try:
        from PyQt6.QtCore import QThread

        if QThread.currentThread() is window.thread():
            return fn()
    except Exception:
        return fn()
    qt = getattr(window, "_control_qt_invoker", None)
    if qt is None:
        return fn()
    try:
        return qt.run(fn, timeout=3.0)
    except Exception:
        return None


def _register_actions(window: MainWindow, surface: ControlSurface) -> None:
    """기능별 등록 조립. 실행은 iris.ui.control_actions."""
    from iris.ui.control_actions.chat import register_chat_actions
    from iris.ui.control_actions.email import register_email_actions
    from iris.ui.control_actions.emulator import register_emulator_actions
    from iris.ui.control_actions.ide import register_ide_actions
    from iris.ui.control_actions.learning import register_learning_actions
    from iris.ui.control_actions.profile import register_profile_actions
    from iris.ui.control_actions.project import register_project_actions
    from iris.ui.control_actions.session import register_session_actions
    from iris.ui.control_actions.settings import register_settings_actions
    from iris.ui.control_actions.wiki import register_wiki_actions
    from iris.ui.control_actions.workspace import register_workspace_actions

    reg = surface.registry
    register_session_actions(window, reg, surface)
    register_ide_actions(window, reg)
    register_project_actions(window, reg)
    register_profile_actions(window, reg)
    register_workspace_actions(window, reg)
    register_emulator_actions(window, reg)
    register_learning_actions(window, reg)
    register_settings_actions(window, reg)
    register_email_actions(window, reg)
    register_wiki_actions(window, reg)
    register_chat_actions(window, reg)
    names = [a["name"] for a in reg.catalog()]
    assert len(names) == len(set(names)), "duplicate control actions"


def _emulator_running() -> bool:
    try:
        from iris.system.android_emulator import is_emulator_process_up

        return bool(is_emulator_process_up())
    except Exception:
        return False


def _mic_state_fields(window: MainWindow) -> dict[str, Any]:
    try:
        from iris.audio.microphone_controller import MicState

        mic = getattr(window, "_mic", None)
        state = getattr(getattr(mic, "state", None), "value", str(getattr(mic, "state", "")))
        listening = bool(
            mic is not None
            and getattr(mic, "state", None) not in (MicState.OFF, MicState.ERROR)
        )
        prefs = getattr(window, "_voice_prefs", None)
        return {
            "state": state,
            "listening": listening,
            "stt_enabled": bool(getattr(prefs, "stt_enabled", False)),
            "preferred": bool(getattr(prefs, "mic_listen_preferred", False)),
        }
    except Exception:
        return {
            "state": "",
            "listening": False,
            "stt_enabled": False,
            "preferred": False,
        }


def _emulator_state_fields() -> dict[str, Any]:
    try:
        from iris.system.android_emulator import emulator_status_fast

        st = emulator_status_fast()
        return {
            "emulator_serial": st.get("serial"),
            "emulator_serials": st.get("serials") or [],
            "emulator_headless": bool(st.get("headless")),
            "emulator_avd": st.get("avd"),
            "emulator_phase": st.get("phase"),
            "emulator_adb_ready": bool(st.get("adb_ready")),
            "emulator_boot_completed": bool(st.get("boot_completed")),
            "emulator_keyboard_hint": st.get("keyboard_hint"),
        }
    except Exception:
        return {
            "emulator_serial": None,
            "emulator_serials": [],
            "emulator_headless": False,
            "emulator_avd": None,
            "emulator_phase": "stopped",
            "emulator_adb_ready": False,
            "emulator_boot_completed": False,
            "emulator_keyboard_hint": None,
        }


# typing alias for stub factory
HandlerFn = Callable[[dict[str, Any]], dict[str, Any]]
