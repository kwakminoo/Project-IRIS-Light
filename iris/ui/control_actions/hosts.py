"""액션 모듈이 요구하는 호스트 속성.

MainWindow가 이 프로토콜을 만족하지만, 액션 모듈은 MainWindow를 import하지 않는다.
실행 스레드: HTTP 워커가 registry.invoke를 부른다. project.run·email.list_messages·email.read_message·emulator.* 만 UI 스레드 밖이다 (iris.system.control_surface.runs_off_ui_thread). 나머지는 Qt 메인 스레드.
반환: ok_result / err_result. 예외는 ActionRegistry.invoke가 err_result로 감싼다.
confirm_required 액션은 args.confirm 이 없으면 거절된다.
"""

from __future__ import annotations

from typing import Any, Protocol


class SessionHost(Protocol):
    _calendar_page: Any
    _db: Any
    _get_bound_ide_session: Any
    _hermes_online: Any
    _selected_email_account_id: Any
    _settings: Any
    _ui_mode: Any
    _workspace_mode: Any


class IdeHost(Protocol):
    _attach_os_drop_paths: Any
    _begin_ide_companion_drag: Any
    _db: Any
    _enter_ide_companion: Any
    _exit_ide_companion: Any
    _finish_ide_companion_drag: Any
    _ide_session: Any
    _on_ide_icon: Any
    _open_ide_folder: Any
    _toggle_maximize: Any
    _ui_mode: Any
    activateWindow: Any
    isMaximized: Any
    isMinimized: Any
    isVisible: Any
    minimize: Any
    raise_: Any
    show: Any
    showMinimized: Any
    showNormal: Any
    toggle_maximize: Any


class ProjectHost(Protocol):
    _db: Any
    _get_bound_ide_session: Any
    _ide_session: Any
    _iris_ide_bridge_client: Any
    _open_ide_folder: Any
    _ui_mode: Any
    diagram_preview: Any


class ProfileHost(Protocol):
    _db: Any


class WorkspaceHost(Protocol):
    _calendar_page: Any
    _db: Any
    _on_calendar_icon: Any
    _on_email_icon: Any
    _on_mobile_icon: Any
    _on_obsidian_icon: Any
    _refresh_calendar_holidays: Any
    _reload_calendar_month: Any
    _settings: Any
    _show_assistant_workspace: Any
    _sync_calendar_wiki: Any
    _workspace_mode: Any


class EmulatorHost(Protocol):
    _live_activity: Any


class LearningHost(Protocol):
    _learning: Any
    _learning_prefs: Any
    _on_learning_toggle: Any
    _start_learning_session: Any
    _stop_learning_session: Any


class SettingsHost(Protocol):
    _apply_selected_model: Any
    _chat: Any
    _open_settings_dialog: Any
    _open_user_profile_dialog: Any
    _refresh_hermes_health: Any
    _settings: Any
    _status_header: Any


class EmailHost(Protocol):
    _current_email_account: Any
    _db: Any
    _email_folder: Any
    _email_page: Any
    _email_preloaded: Any
    _load_email_message: Any
    _on_email_account_changed: Any
    _on_email_category: Any
    _on_email_folder_selected: Any
    _on_email_icon: Any
    _open_email_compose: Any
    _refresh_email_inbox: Any
    _selected_email_account_id: Any
    _send_email: Any
    _workspace_mode: Any


class WikiHost(Protocol):
    _chat: Any
    _iris_wiki: Any
    _left_sidebar: Any
    _obsidian_page: Any
    _on_obsidian_icon: Any
    _saved_model: Any
    _settings: Any
    _workspace_mode: Any


class ChatHost(Protocol):
    _apply_selected_model: Any
    _chat: Any
    _conversation_id: Any
    _db: Any
    _live_activity: Any
    _mic: Any
    _notes: Any
    _on_chat_mic_clicked: Any
    _on_chat_stop: Any
    _on_conversation_selected: Any
    _on_new_chat_requested: Any
    _set_mic_listen: Any
    _voice_prefs: Any
    reset_current_conversation: Any
