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
from iris.system.execution_context import (
    ExecutionContext,
    active_turn_id,
    execution_context_from_control,
    frozen_turn_execution_context,
    store_turn_execution_context,
)
from iris.system.ide_launcher import ide_catalog, is_ide_installed
from iris.system.patch_buffer_sync import IdePatchBufferSync, set_patch_buffer_sync
from iris.learning.permission import policy_for
from iris.ui.chat.run_visibility import card_from_control_result, insert_visibility_card

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

    def run(self, fn: Callable[[], Any], timeout: float | None = 15.0) -> Any:
        box: dict[str, Any] = {"event": threading.Event()}
        self._call.emit(fn, box)
        if timeout is None:
            box["event"].wait()
        elif not box["event"].wait(timeout):
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


def iris_ide_editor_opened(bridge_out: Any) -> tuple[bool, str]:
    """True only when IRIS IDE poller opened a tab. Soft-success paths are gone."""
    if not isinstance(bridge_out, dict):
        return False, "empty bridge open result"
    if bridge_out.get("via") == "bridge_fallback":
        return False, str(
            bridge_out.get("error")
            or "IDE editor did not open (obsolete bridge_fallback)"
        )
    if bridge_out.get("opened") is False:
        return False, str(bridge_out.get("error") or "IDE editor did not open")
    viewer = bridge_out.get("viewer")
    if viewer is not None and viewer not in ("iris.pdf", "monaco"):
        return False, f"unsupported IDE viewer: {viewer}"
    return True, ""


def iris_ide_save_ok(bridge_out: Any) -> tuple[bool, str]:
    """True only when the editor buffer was flushed. Disk-only is not a save."""
    if not isinstance(bridge_out, dict):
        return False, "empty bridge save result"
    if bridge_out.get("saved") is not True:
        return False, str(bridge_out.get("reason") or bridge_out.get("error") or "save failed")
    if bridge_out.get("via") == "disk" or bridge_out.get("editor") is False:
        return False, "IRIS IDE editor did not save (no open editor buffer)"
    return True, ""


def iris_ide_edit_ok(bridge_out: Any) -> tuple[bool, str]:
    """True only when Monaco applied the edit. Disk append is not a selection replace."""
    if not isinstance(bridge_out, dict):
        return False, "empty bridge edit result"
    if bridge_out.get("noEditor") is True:
        return False, "IRIS IDE editor did not apply buffer edit (no open editor)"
    if bridge_out.get("via") != "editor":
        return False, "IRIS IDE buffer edit requires via=editor (disk append is not a selection replace)"
    return True, ""


def iris_ide_query_ok(bridge_out: Any) -> tuple[bool, str]:
    """True only after a language-service query finished. Empty items need queried true."""
    if not isinstance(bridge_out, dict):
        return False, "empty bridge language-query result"
    if bridge_out.get("queried") is not True:
        return False, str(
            bridge_out.get("error")
            or bridge_out.get("reason")
            or "language service did not complete a query"
        )
    return True, ""


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
            visible, open_err = iris_ide_editor_opened(out)
            if not visible:
                return {
                    "ok": False,
                    "path": path,
                    "error": open_err,
                    "line": line,
                    "column": column,
                    "visible": False,
                    "bridge": out,
                    "via": (out or {}).get("via") if isinstance(out, dict) else None,
                    "viewer": (out or {}).get("viewer") if isinstance(out, dict) else None,
                }
            return {
                "ok": True,
                "path": path,
                "error": None,
                "line": line,
                "column": column,
                "visible": True,
                "bridge": out,
                "viewer": (out or {}).get("viewer") if isinstance(out, dict) else None,
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


def _session_workspace_for_capture(window: Any) -> tuple[str, str]:
    """Best-effort workspace_root/id for Trusted ExecutionContext (no model args)."""
    workspace_root = ""
    session = None
    getter = getattr(window, "_get_bound_ide_session", None)
    if callable(getter):
        try:
            session = getter(refresh=False)
        except TypeError:
            try:
                session = getter()
            except Exception:  # noqa: BLE001 — offline / tests
                session = None
        except Exception:  # noqa: BLE001
            session = None
    if session is None:
        try:
            session, _err = _bound_session(window, require_workspace=False)
        except Exception:  # noqa: BLE001 — offline / no IDE
            session = None
    if session is not None:
        workspace_root = str(getattr(session, "workspace_root", "") or "")
    return workspace_root, workspace_root


def capture_execution_context(
    window: Any, *, turn_id: str = ""
) -> ExecutionContext:
    """Snapshot live Control window bind into ExecutionContext (not from Speak args)."""
    sid = str(getattr(window, "_conversation_id", "") or "")
    workspace_root, workspace_id = _session_workspace_for_capture(window)
    return execution_context_from_control(
        session_id=sid,
        conversation_id=sid,
        turn_id=str(turn_id or ""),
        workspace_id=workspace_id,
        workspace_root=workspace_root,
        surface="control",
        principal="iris.control",
        permission_scope="session",
    )


def freeze_turn_execution_context(window: Any, turn_id: str) -> ExecutionContext:
    """HF-03: freeze Trusted ExecutionContext at Agent Turn begin."""
    tid = str(turn_id or "").strip()
    ctx = capture_execution_context(window, turn_id=tid)
    return store_turn_execution_context(window, tid, ctx)


def trusted_execution_context(window: Any) -> ExecutionContext:
    """Handlers: prefer turn-frozen ctx; else live capture (legacy unscoped)."""
    frozen = frozen_turn_execution_context(window)
    if frozen is not None:
        return frozen
    return capture_execution_context(window, turn_id=active_turn_id(window))


def resolve_bound_work_root(
    window: MainWindow,
    args: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """쓰기·실행·목록 루트. 기본은 화면에 연 bound workspace. profile.project_root sticky 금지.

    Returns (root, err). err 비어 있으면 root 사용.
    명시 project_root/root/cwd 가 있으면 그걸 쓰고, ensure_iris_ide_workspace 가 IDE 를 맞춘다.
    """
    args = args or {}
    explicit = str(
        args.get("project_root") or args.get("root") or args.get("cwd") or ""
    ).strip()
    bound = ""
    try:
        session = window._get_bound_ide_session(refresh=False)
        if session is not None and str(session.workspace_root or "").strip():
            bound = str(Path(str(session.workspace_root)).expanduser().resolve())
    except Exception:
        bound = ""
    raw = explicit or bound
    if not raw:
        return (
            "",
            "bound IDE workspace required (open a folder in the IDE first)",
        )
    from iris.runtime.chat_worktree import conversation_id_of, work_root_for

    rooted = work_root_for(conversation_id_of(window, args), raw)
    if not rooted:
        return "", "work root empty after worktree resolve"
    try:
        return str(Path(rooted).expanduser().resolve()), ""
    except OSError:
        return "", f"invalid work root: {rooted}"


def ensure_iris_ide_workspace(
    window: Any,
    work_root: str | Path,
    *,
    action: str,
    open_folder: Callable[[str], str] | None = None,
    new_window: bool = False,
) -> dict[str, Any] | None:
    """work_root 와 bound workspace 를 맞춘다. None = 진행 가능, dict = err_result.

    이미 일치하면 open_folder 를 호출하지 않는다(멱등).
    불일치면 기존 _open_ide_folder 경로로 맞추고, 맞춘 뒤 다시 확인한다.
    new_window 기본 False: 이미 bound 된 Companion 에서 폴더만 바꾼다(새 창 spawn 금지).
    """
    try:
        root_s = str(Path(str(work_root)).expanduser().resolve())
    except OSError:
        root_s = str(Path(str(work_root)).expanduser())
    session, session_err = _bound_session(window, require_workspace=True)
    if session_err or session is None:
        return err_result(
            action,
            session_err or "bound IDE workspace session required",
            {
                "project_root": root_s,
                "bound_workspace_root": None,
                "open_folder_path": root_s,
                "hint": "ide.open_folder",
            },
        )
    try:
        bound = str(Path(session.workspace_root).resolve())
    except OSError:
        bound = str(session.workspace_root or "")
    if bound == root_s:
        return None

    def _default_open(path: str) -> str:
        # 액션 스레드에서 직접 호출(기존 open_similar 와 동일). Queued _call_on_ui(3s)로
        # 동기 open_folder 를 감싸면 타임아웃·재진입 함정.
        err = window._open_ide_folder(path, new_window=new_window, source="chat")
        return str(err or "")

    opener = open_folder if open_folder is not None else _default_open
    try:
        open_err = opener(root_s)
    except Exception as exc:  # noqa: BLE001
        open_err = str(exc)
    open_err_s = str(open_err or "").strip()
    if open_err_s:
        return err_result(
            action,
            f"failed to align IDE workspace to project_root: {open_err_s}",
            {
                "project_root": root_s,
                "bound_workspace_root": bound,
                "open_folder_path": root_s,
                "error": open_err_s,
                "hint": "ide.open_folder",
            },
        )

    session2, session2_err = _bound_session(window, require_workspace=True)
    if session2_err or session2 is None:
        return err_result(
            action,
            session2_err or "IDE workspace missing after open_folder",
            {
                "project_root": root_s,
                "bound_workspace_root": bound,
                "open_folder_path": root_s,
                "error": session2_err or "missing session",
                "hint": "ide.open_folder",
            },
        )
    try:
        bound2 = str(Path(session2.workspace_root).resolve())
    except OSError:
        bound2 = str(session2.workspace_root or "")
    if bound2 != root_s:
        return err_result(
            action,
            "IDE workspace still mismatched after open_folder",
            {
                "project_root": root_s,
                "bound_workspace_root": bound2,
                "open_folder_path": root_s,
                "error": "workspace_root did not update",
                "hint": "ide.open_folder",
            },
        )
    return None


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
    브리지 openFile이 OpenFileBudget(15s) 안에 응답하지 못하면 하드 오류다 (가짜 open 없음).
    이 펌프 상한(기본 20s)은 15s 프론트 대기보다 길게 둔다.
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
    # 데드락 나며 Windows "응답 없음"이 됨. IrisAgentHealthWorker가 백그라운드에서 동기화.
    window._control_surface = surface  # type: ignore[attr-defined]
    window._control_qt_invoker = qt  # type: ignore[attr-defined]
    from iris.infrastructure.speak_capability import bind_live_control_surface

    bind_live_control_surface(surface)
    window._live_activity.append_instant_line(
        f"Iris control: listening on http://{host}:{bound} (SpeakTools only)"
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
        from iris.infrastructure.speak_capability import bind_live_control_surface

        bind_live_control_surface(None)


def mark_control_ready(window: MainWindow) -> None:
    surface = getattr(window, "_control_surface", None)
    if surface is not None:
        surface.booting = False


def _log(window: MainWindow, action: str, ok: bool) -> None:
    status = "ok" if ok else "fail"
    _append_activity(window, f"Iris control: {action} {status}")


def _with_run_visibility(
    window: MainWindow,
    action_name: str,
    action: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """project.run / write_file 결과를 채팅 ToolShellBlock으로 남긴다 (RunVisibility)."""

    def _wrapped(args: dict[str, Any]) -> dict[str, Any]:
        result = action(args)
        try:
            card = card_from_control_result(action_name, result if isinstance(result, dict) else {})
            if card is None:
                return result

            def _do() -> None:
                chat = getattr(window, "_chat", None)
                if chat is not None:
                    insert_visibility_card(chat, card)

            _call_on_ui(window, _do)
        except Exception:
            pass
        return result

    return _wrapped


def _first_class_ide_trigger(
    window: MainWindow, action: Callable[[dict[str, Any]], dict[str, Any]]
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """액션 성공을 이번 턴의 IDE 개방 트리거로 확정한다 (연번 11).

    성공 반환 지점이 여러 곳이라 등록 시점에 감싼다.
    """

    def _wrapped(args: dict[str, Any]) -> dict[str, Any]:
        result = action(args)
        inner = result.get("result") if isinstance(result.get("result"), dict) else {}
        if "content_match" in inner:
            window._turn_content_match = bool(inner.get("content_match"))
        elif result.get("content_match") is False:
            window._turn_content_match = False
        path = str(inner.get("path") or "")
        # Policy A: open fail with on_disk still counts as wrote for CHAT_ONLY/Verify.
        on_disk = bool(inner.get("on_disk")) and bool(path) and Path(path).is_file()
        if result.get("ok") or on_disk:
            if path and Path(path).is_file():
                window._turn_write_path = path
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


def _call_on_ui_unbounded(window: MainWindow, fn: Callable[[], Any]) -> Any:
    """HUD confirm waits until the dialog returns. The 3s UI marshal is too short."""
    try:
        from PyQt6.QtCore import QThread

        if QThread.currentThread() is window.thread():
            return fn()
    except Exception:
        return fn()
    qt = getattr(window, "_control_qt_invoker", None)
    if qt is None:
        return fn()
    return qt.run(fn, timeout=None)


def _confirm_body(spec: Any, args: dict[str, Any]) -> str:
    bits = [spec.summary or spec.name]
    for key in ("to", "destination", "subject", "text", "url", "value", "name"):
        if args.get(key):
            bits.append(f"{key}={args[key]}")
    return "\n".join(bits)[:800]


def _card_preview_command(name: str, args: dict[str, Any]) -> str:
    """Pending-card body. Newlines keep allowlist_key empty (no Always Allow scope)."""
    payload = args if isinstance(args, dict) else {}
    if name == "email.send" or name.startswith("email."):
        bits = [name]
        # Never preview password / secrets on the card.
        for key in ("to", "subject", "body", "address", "label", "account_id"):
            val = str(payload.get(key) or "").strip()
            if not val:
                continue
            if key == "body" and len(val) > 200:
                val = val[:200] + "…"
            bits.append(f"{key}={val}")
        return "\n".join(bits)[:800]
    if name.startswith("browser."):
        bits = [name]
        url = str(payload.get("url") or "").strip()
        click = str(
            payload.get("name")
            or payload.get("text")
            or payload.get("value")
            or payload.get("ref")
            or ""
        ).strip()
        if url:
            bits.append(f"url={url}")
        if click:
            bits.append(f"click={click}")
        risk = str(payload.get("risk") or "").strip()
        if risk:
            bits.append(f"risk={risk}")
        return "\n".join(bits)[:800] if len(bits) > 1 else name
    from iris.ui.chat.shell_approval import preview_command

    return preview_command(payload)


def _card_title(name: str, spec: Any) -> str:
    if "write" in name:
        base = "Write"
    elif name.startswith("email."):
        base = "Email"
    elif name.startswith("browser."):
        base = "Browser"
    else:
        base = "Shell"
    risk = str(getattr(spec, "risk", "") or "").strip()
    if risk in ("high", "critical"):
        return f"{base} · {risk}"
    return base


def _uses_card_confirm(name: str) -> bool:
    return name in _CARD_CONFIRM_ACTIONS or name.startswith("browser.")


def _fail_closed_card(name: str) -> bool:
    """No HUD fallback when card insert fails (EXTERNAL / SENSITIVE / shell)."""
    return name in _SHELL_NO_HUD_ACTIONS or name.startswith("browser.")


def _allow_card_auto(name: str) -> bool:
    """Shell Run Everything must not auto-approve EXTERNAL_EFFECT / SENSITIVE."""
    if name.startswith("email.") or name.startswith("browser."):
        return False
    return True


# write/run/email: 채팅 카드 승인 가능하면 HUD 대신 (15s UI timeout·모달만 의존 금지)
_CARD_CONFIRM_ACTIONS = frozenset(
    {
        "shell.run",
        "project.run",
        "local.write_file",
        "project.write_file",
        "email.send",
        "email.add_account",
        "email.remove_account",
    }
)

# Card-only fail-closed (no HUD). write may still HUD; email/shell never.
_SHELL_NO_HUD_ACTIONS = frozenset(
    {
        "shell.run",
        "project.run",
        "email.send",
        "email.add_account",
        "email.remove_account",
    }
)


def human_confirm_decision(
    spec: Any,
    args: dict[str, Any],
    *,
    chat: Any | None,
    ask_hud: Callable[[], bool],
    on_ui: Callable[[Callable[[], Any]], Any],
    wait: Callable[[str], str] | None = None,
    load_approval: Callable[[], Any] | None = None,
    on_attention: Callable[[], None] | None = None,
) -> bool:
    """ConfirmPath: card gate for shell/run/email/browser; write may HUD; fail-closed set never HUD."""
    name = str(getattr(spec, "name", "") or "")
    if _uses_card_confirm(name):
        from iris.ui.chat.shell_approval import load
        from iris.ui.chat.shell_gate import stash_shell_confirm_block, take, try_card_confirm

        approval_fn = load if load_approval is None else load_approval
        wait_fn = take if wait is None else wait
        payload = args if isinstance(args, dict) else {}
        command = _card_preview_command(name, payload)
        title = _card_title(name, spec)
        decided = try_card_confirm(
            chat=chat,
            command=command,
            title=title,
            approval=approval_fn(),
            wait=wait_fn,
            on_ui=on_ui,
            on_attention=on_attention,
            allow_auto=_allow_card_auto(name),
        )
        if decided.approved is not None:
            if name in ("shell.run", "project.run") and decided.approved:
                rid = stash_shell_confirm_block(
                    chat, decided.block_id, command=command
                )
                if isinstance(args, dict) and rid:
                    args["_iris_shell_request_id"] = rid
            return bool(decided.approved)
        # Card unavailable: fail-closed actions never HUD.
        if _fail_closed_card(name):
            if isinstance(args, dict):
                args["_iris_confirm_deny"] = "approval_ui_unavailable"
            return False
    return bool(ask_hud())


def _register_actions(window: MainWindow, surface: ControlSurface) -> None:
    """기능별 등록 조립. 실행은 iris.ui.control_actions."""
    from iris.ui.control_actions.attachment import register_attachment_actions
    from iris.ui.control_actions.agent_turn import register_agent_turn_actions
    from iris.ui.control_actions.app import register_app_actions
    from iris.ui.control_actions.chat import register_chat_actions
    from iris.ui.control_actions.email import register_email_actions
    from iris.ui.control_actions.browser import register_browser_actions
    from iris.ui.control_actions.emulator import register_emulator_actions
    from iris.ui.control_actions.ide import register_ide_actions
    from iris.ui.control_actions.learning import register_learning_actions
    from iris.ui.control_actions.local_files import register_local_file_actions
    from iris.ui.control_actions.profile import register_profile_actions
    from iris.ui.control_actions.project import register_project_actions
    from iris.ui.control_actions.session import register_session_actions
    from iris.ui.control_actions.routine import register_routine_actions
    from iris.ui.control_actions.settings import register_settings_actions
    from iris.ui.control_actions.process import register_process_actions
    from iris.ui.control_actions.shell import register_shell_actions
    from iris.ui.control_actions.web import register_web_actions
    from iris.ui.control_actions.wiki import register_wiki_actions
    from iris.ui.control_actions.workspace import register_workspace_actions

    reg = surface.registry
    register_session_actions(window, reg, surface)
    register_attachment_actions(window, reg)
    register_local_file_actions(window, reg)
    register_shell_actions(window, reg)
    register_process_actions(window, reg)
    register_web_actions(window, reg)
    register_ide_actions(window, reg)
    register_project_actions(window, reg)
    # Wave 1.2 U10 — wire Theia buffer reload to apply_patch (dirty refuse + post-commit sync).
    set_patch_buffer_sync(IdePatchBufferSync(lambda: _iris_ide_client(window)))
    register_profile_actions(window, reg)
    register_workspace_actions(window, reg)
    register_emulator_actions(window, reg)
    register_browser_actions(window, reg)
    register_learning_actions(window, reg)
    register_routine_actions(window, reg)
    register_settings_actions(window, reg)
    register_email_actions(window, reg)
    register_wiki_actions(window, reg)
    register_chat_actions(window, reg)
    register_app_actions(window, reg)
    register_agent_turn_actions(window, reg)
    from iris.ui.settings.hud_dialog import run_hud_confirm

    def _human_confirm(spec: Any, args: dict[str, Any]) -> bool:
        def _ask() -> bool:
            return run_hud_confirm(
                None,
                title=spec.name,
                body=_confirm_body(spec, args),
                hint="모델이 확인을 대신할 수 없습니다.",
                badge="CONFIRM",
                ok_text="실행",
                cancel_text="취소",
                default_ok=False,
            )

        from iris.ui.chat.shell_gate import _raise_attention

        return human_confirm_decision(
            spec,
            args,
            chat=getattr(window, "_chat", None),
            ask_hud=lambda: bool(_call_on_ui_unbounded(window, _ask)),
            on_ui=lambda fn: _call_on_ui_unbounded(window, fn),
            on_attention=lambda: _raise_attention(window),
        )

    reg.set_human_confirm(_human_confirm)
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


def _browser_state_fields() -> dict[str, Any]:
    try:
        from iris.browser.session import get_browser_session
        from iris.browser.types import BrowserPhase

        snap = get_browser_session().snapshot()
        return {
            "browser_open": snap.phase != BrowserPhase.CLOSED,
            "browser_url": snap.url,
            "browser_title": snap.title,
            "browser_phase": snap.phase.value,
            "mini_player": bool(snap.mini_player),
            "browser_playing": bool(snap.media and snap.media.playing),
            "browser_media_block": (snap.media.block if snap.media else "") or "",
            "browser_target": snap.target_id or f"tab:{snap.tab_index}",
            "browser_tab_index": snap.tab_index,
            "browser_tab_count": snap.tab_count,
        }
    except Exception:
        return {
            "browser_open": False,
            "browser_url": "",
            "browser_title": "",
            "browser_phase": "closed",
            "mini_player": False,
            "browser_playing": False,
            "browser_media_block": "",
            "browser_target": "tab:0",
            "browser_tab_index": 0,
            "browser_tab_count": 1,
        }


# typing alias for stub factory
HandlerFn = Callable[[dict[str, Any]], dict[str, Any]]
