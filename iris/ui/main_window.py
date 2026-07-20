"""메인 PyQt6 창 — Ollama 모델 선택 + Hermes/Ollama 채팅."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, QThread, QTimer
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from iris.config.settings import load_settings
from iris.core.activity_sink import register_activity_sink
from iris.core.state_machine import AppState, StateMachine
from iris.infrastructure.ollama_client import OllamaModelInfo
from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.email_accounts import load_email_accounts
from iris.monitoring.notification_policy import NotificationPolicy
from iris.storage.database import Database
from iris.storage.model_prefs import load_selected_model, save_selected_model
from iris.system.android_emulator import is_emulator_running, launch_emulator
from iris.system.metrics_worker import MetricsWorker
from iris.ui.chat_panel import ChatPanel
from iris.ui.cyberspace_background import CyberspaceBackground
from iris.ui.cyberspace_theme import apply_cyberspace_theme
from iris.ui.drag_tab import DragTab
from iris.ui.frameless_chrome import FramelessShell, center_on_screen, suppress_native_window_border
from iris.ui.left_sidebar_panel import LeftSidebarPanel
from iris.ui.live_activity_panel import LiveActivityPanel, UiActivityRelay
from iris.ui.notification_panel import NotificationPanel
from iris.ui.email_workers import EmailInboxWorker, EmailMessageWorker, EmailSendWorker
from iris.ui.hermes_workers import (
    HermesChatWorker,
    HermesHealthWorker,
    HermesModelSyncWorker,
)
from iris.ui.ollama_workers import OllamaChatWorker, OllamaModelListWorker
from iris.ui.settings_dialog import SettingsDialog
from iris.ui.startup_intro import StartupIntroAnimator
from iris.ui.theme_tokens import TOKENS
from iris.ui.top_status_header import TopStatusHeader
from iris.ui.unified_monitor_panel import UnifiedMonitorPanel
from iris.ui.user_profile_dialog import UserProfileDialog
from iris.ui.visualizer import Visualizer
from iris.ui.workspaces.assistant_workspace_page import AssistantWorkspacePage
from iris.ui.workspaces.email_workspace_page import EmailWorkspacePage
from iris.ui.workspaces.obsidian_workspace_page import ObsidianWorkspacePage


class MainWindow(QMainWindow):
    """Iris Light — Hermes API 또는 Ollama 채팅 HUD."""

    def __init__(self, *, test_mode: bool = False) -> None:
        super().__init__()
        self._test_mode = test_mode
        self.setWindowTitle("Iris Light")
        self.setMinimumSize(960, 640)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._env_path = Path(__file__).resolve().parents[2] / ".env"
        self._settings = load_settings(self._env_path)
        if self._test_mode:
            test_db_dir = Path.cwd() / ".iris_light_test_tmp"
            test_db_dir.mkdir(parents=True, exist_ok=True)
            self._db = Database(test_db_dir / "main_window_test.db")
        else:
            self._db = Database()

        self._state = StateMachine()
        self._state.state_changed.connect(self._on_app_state)
        self._history: list[dict[str, str]] = []
        self._chat_worker: QThread | None = None
        self._model_worker: OllamaModelListWorker | None = None
        self._hermes_health_worker: HermesHealthWorker | None = None
        self._hermes_model_worker: HermesModelSyncWorker | None = None
        self._email_inbox_worker: EmailInboxWorker | None = None
        self._email_message_worker: EmailMessageWorker | None = None
        self._email_send_worker: EmailSendWorker | None = None
        self._selected_email_account_id = ""
        self._hermes_online = False
        self._busy = False
        self._workspace_mode = "assistant"
        self._intro: StartupIntroAnimator | None = None
        self._saved_model = load_selected_model(self._db) or self._settings.ollama_model.strip()
        if self._saved_model:
            self._settings.ollama_model = self._saved_model
            self._settings.model_name = self._saved_model

        central = CyberspaceBackground()
        self._cyberspace_bg = central
        self._viz = Visualizer(central)

        ui_overlay = QWidget()
        ui_overlay.setObjectName("UiOverlay")
        self._ui_overlay = ui_overlay
        central.set_orb_layer(self._viz)
        central.set_ui_overlay(ui_overlay)

        root = QVBoxLayout(ui_overlay)
        root.setContentsMargins(
            TOKENS.spacing_lg,
            TOKENS.spacing_sm,
            TOKENS.spacing_lg,
            TOKENS.spacing_sm,
        )
        root.setSpacing(TOKENS.spacing_sm)

        self._drag = DragTab(self)
        self._drag.profile_clicked.connect(self._open_user_profile_dialog)
        self._drag.settings_clicked.connect(self._open_settings_dialog)
        self._drag.minimize_clicked.connect(self.showMinimized)
        self._drag.maximize_clicked.connect(self._toggle_maximize)
        root.addWidget(self._drag)

        status_header = TopStatusHeader()
        self._status_header = status_header
        status_header.set_model_name(
            self._settings.model_name or self._settings.ollama_model or "(unset)"
        )
        status_header.set_tts_status("OFF")
        status_header.set_app_state(AppState.IDLE)
        self._refresh_hermes_health()
        self._drag.place_status_rows(
            status_header.status_widget(),
            status_header.backend_row(),
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(0)

        self._left_sidebar = LeftSidebarPanel()
        splitter.addWidget(self._left_sidebar)

        self._workspace_stack = QStackedWidget()
        self._assistant_page = AssistantWorkspacePage()
        self._obsidian_page = ObsidianWorkspacePage()
        self._email_page = EmailWorkspacePage()
        self._workspace_stack.addWidget(self._assistant_page)
        self._workspace_stack.addWidget(self._obsidian_page)
        self._workspace_stack.addWidget(self._email_page)
        splitter.addWidget(self._workspace_stack)

        self._iris_wiki = IrisWiki(Path(__file__).resolve().parents[2] / "obsidian-vault")
        self._obsidian_page.set_wiki(self._iris_wiki)
        self._left_sidebar.obsidian_detail.set_wiki(self._iris_wiki)
        self._left_sidebar.obsidian_detail.note_selected.connect(self._obsidian_page.show_note)
        self._email_page.account_changed.connect(self._on_email_account_changed)
        self._email_page.refresh_requested.connect(self._refresh_email_inbox)
        self._email_page.compose_requested.connect(self._send_email)
        self._left_sidebar.email_detail.mail_selected.connect(self._load_email_message)

        left_lay = self._assistant_page.center_layout
        right_lay = self._assistant_page.right_layout

        self._orb_spacer = QWidget()
        self._orb_spacer.setObjectName("OrbLayoutSpacer")
        self._orb_spacer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._orb_spacer.setMinimumHeight(160)
        self._orb_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        left_lay.addWidget(self._orb_spacer, 2)
        self._viz.set_orb_anchor(self._orb_spacer)
        self._viz.register_geometry_watch(
            self._orb_spacer,
            self._assistant_page.center_column,
            self._assistant_page,
            self._assistant_page.splitter,
            ui_overlay,
            central,
            self,
        )

        self._activity_relay = UiActivityRelay(self)
        self._live_activity = LiveActivityPanel(self)
        self._activity_relay.line.connect(self._live_activity.enqueue_typed_line)
        register_activity_sink(self._activity_relay.push)
        left_lay.addWidget(self._live_activity, 0)

        self._chat = ChatPanel()
        self._chat.set_speech_threshold_rms(self._settings.always_listen_speech_rms)
        self._chat.send_clicked.connect(self._on_user_text)
        self._chat.model_changed.connect(self._on_model_changed)
        left_lay.addWidget(self._chat, 3)

        self._monitor = UnifiedMonitorPanel()
        self._monitor.set_database(self._db)
        self._monitor.setMinimumHeight(160)

        self._notif_policy = NotificationPolicy(self._db)
        self._notes = NotificationPanel(policy=self._notif_policy)
        self._notes.setMinimumHeight(120)
        right_lay.addWidget(self._monitor, 2)
        right_lay.addWidget(self._notes, 1)

        splitter.setSizes([220, 1160])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)

        actions = self._left_sidebar.utility.actions
        actions.set_default_callback(self._show_assistant_workspace)
        for action_id, icon_kind, tooltip in (
            ("ide", "ide", "IDE (준비 중)"),
            ("email", "email", "이메일"),
            ("mobile", "mobile", "Android 에뮬레이터"),
            ("instagram", "instagram", "Instagram (준비 중)"),
            ("discord", "discord", "Discord (준비 중)"),
            ("kakao", "kakao", "카카오톡 (준비 중)"),
            ("obsidian", "obsidian", "Iris Wiki"),
            ("telegram", "telegram", "텔레그램 (준비 중)"),
        ):
            callback = None
            if action_id == "mobile":
                callback = self._on_mobile_icon
            elif action_id == "email":
                callback = self._on_email_icon
            elif action_id == "obsidian":
                callback = self._on_obsidian_icon
            actions.add_icon_action(
                action_id=action_id,
                icon_kind=icon_kind,
                tooltip=tooltip,
                callback=callback,
            )

        self._metrics_worker = MetricsWorker(parent=self)
        self._metrics_worker.snapshot_ready.connect(self._on_metrics_snapshot)
        if not self._test_mode:
            self._metrics_worker.start()

        root.addWidget(splitter, 1)

        shell = FramelessShell(self)
        shell.set_center_widget(central)
        self.setCentralWidget(shell)
        apply_cyberspace_theme(self)

        act_quit = QAction("종료", self)
        act_quit.triggered.connect(self.close)
        self.addAction(act_quit)

        self.resize(1280, 800)
        center_on_screen(self)

        if not self._test_mode:
            self._intro = StartupIntroAnimator(self)
            self._intro.bind(
                left=self._left_sidebar,
                right=self._assistant_page.right_column,
                orb=self._viz.particle_core(),
                live=self._live_activity,
                chat=self._chat,
                waveform=self._chat.waveform,
                chrome=[self._drag],
            )
            self._intro.finished.connect(self._on_intro_finished)
            self._viz.particle_core().set_boot_reveal(0.0)
            self._viz.particle_core().set_boot_glitch(1.0)
            self._chat.waveform.set_reveal_progress(0.0)
            self._intro.prepare_hidden()
            QTimer.singleShot(40, self._begin_boot_sequence)
        else:
            self._chat.append_message("Iris", self._ready_status_message())

    def _begin_boot_sequence(self) -> None:
        """빈 창에서 UI 등장 연출 + 무료 모델 확인을 동시에 시작."""
        if self._intro is not None:
            self._intro.start()
        self._refresh_models()

    def _ready_status_message(self) -> str:
        model = (
            self._chat.current_model()
            or self._saved_model
            or self._settings.ollama_model
            or self._settings.model_name
            or "(미선택)"
        ).strip()
        if model in ("", "(unset)"):
            model = "(미선택)"
        return f"아이리스 준비완료 모델: {model} 응답 대기중"

    def _on_intro_finished(self) -> None:
        self._chat.append_message("Iris", self._ready_status_message())
        QTimer.singleShot(200, self._seed_demo_alert)

    def _seed_demo_alert(self) -> None:
        self._notes.try_add_alert(
            target_id=0,
            category="NORMAL",
            title="Iris Light",
            message="Ollama 모델 목록이 연결되었습니다. Hermes 사용 시 gateway를 켜 주세요.",
            focus_hint="",
            event_id=0,
        )

    def _refresh_hermes_health(self) -> None:
        if not self._settings.hermes_enabled:
            self._hermes_online = False
            self._status_header.refresh_backend_status(
                self._settings,
                hermes_online=False,
            )
            return
        if self._hermes_health_worker is not None and self._hermes_health_worker.isRunning():
            return
        worker = HermesHealthWorker(
            self._settings.hermes_base_url,
            api_key=self._settings.hermes_api_key,
            command=self._settings.hermes_command,
            parent=self,
        )
        self._hermes_health_worker = worker
        worker.finished_ok.connect(self._on_hermes_health)
        worker.failed.connect(self._on_hermes_health_failed)
        worker.start()

    def _on_hermes_health(self, online: object) -> None:
        self._hermes_online = bool(online)
        self._status_header.refresh_backend_status(
            self._settings,
            hermes_online=self._hermes_online,
        )
        self._hermes_health_worker = None

    def _on_hermes_health_failed(self, _err: str) -> None:
        self._hermes_online = False
        self._status_header.refresh_backend_status(
            self._settings,
            hermes_online=False,
        )
        self._hermes_health_worker = None

    def _sync_hermes_model(self, model: str) -> None:
        if not self._settings.hermes_enabled:
            return
        model = (model or "").strip()
        if not model:
            return
        if self._hermes_model_worker is not None and self._hermes_model_worker.isRunning():
            return
        worker = HermesModelSyncWorker(
            self._settings.hermes_base_url,
            model,
            api_key=self._settings.hermes_api_key,
            command=self._settings.hermes_command,
            parent=self,
        )
        self._hermes_model_worker = worker
        worker.finished_ok.connect(self._on_hermes_model_synced)
        worker.failed.connect(self._on_hermes_model_sync_failed)
        worker.start()

    def _on_hermes_model_synced(self) -> None:
        model = self._chat.current_model() or self._settings.ollama_model
        self._live_activity.append_instant_line(f"Hermes model synced: {model}")
        self._hermes_model_worker = None

    def _on_hermes_model_sync_failed(self, err: str) -> None:
        self._live_activity.append_instant_line(f"Hermes model sync failed: {err[:160]}")
        self._hermes_model_worker = None

    def _refresh_models(self) -> None:
        if self._model_worker is not None and self._model_worker.isRunning():
            return
        self._chat.set_model_status("(무료 클라우드 모델 확인 중…)")
        worker = OllamaModelListWorker(self._settings.ollama_base_url, parent=self)
        self._model_worker = worker
        worker.finished_ok.connect(self._on_models_loaded)
        worker.failed.connect(self._on_models_failed)
        worker.start()

    def _on_models_loaded(self, models: object) -> None:
        items: list[OllamaModelInfo] = list(models) if isinstance(models, list) else []
        preferred = (
            self._saved_model
            or self._settings.ollama_model
            or self._settings.model_name
        )
        if preferred in ("(unset)",):
            preferred = ""
        self._chat.set_models(items, selected=preferred)
        if items:
            chosen = self._chat.current_model()
            self._apply_selected_model(chosen, persist=False)
            self._live_activity.append_instant_line(
                f"Free cloud models: {len(items)} loaded from ollama.com"
            )
            if self._settings.hermes_enabled and chosen:
                self._sync_hermes_model(chosen)
        else:
            self._chat.set_model_status("(무료 클라우드 모델 없음)")
        if self._intro is not None:
            self._intro.notify_models_ready()

    def _on_models_failed(self, err: str) -> None:
        self._chat.set_model_status("(Ollama 연결 실패)")
        self._live_activity.append_instant_line(f"Model list failed: {err}")
        self._notes.try_add_alert(
            target_id=0,
            category="ERROR_DETECTED",
            title="Ollama",
            message=err[:200],
            focus_hint="",
            event_id=0,
        )
        if self._intro is not None:
            self._intro.notify_models_ready()

    def _on_model_changed(self, model: str) -> None:
        self._apply_selected_model(model, persist=True)

    def _apply_selected_model(self, model: str, *, persist: bool) -> None:
        model = (model or "").strip()
        if not model:
            return
        self._settings.ollama_model = model
        self._settings.model_name = model
        self._saved_model = model
        self._status_header.set_model_name(model)
        if persist:
            save_selected_model(self._db, model)
        if self._settings.hermes_enabled:
            self._sync_hermes_model(model)

    def _use_hermes_backend(self) -> bool:
        return bool(self._settings.hermes_enabled)

    def _backend_label(self) -> str:
        return "Hermes" if self._use_hermes_backend() else "Ollama"

    def _on_user_text(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self._busy:
            self._live_activity.append_instant_line("Busy — wait for the current reply.")
            return
        model = self._chat.current_model()
        if not model:
            self._chat.append_message_instant(
                "Iris",
                "사용할 모델을 선택해 주세요. Ollama가 실행 중인지 확인한 뒤 설정을 열어 보세요.",
            )
            self._refresh_models()
            return
        if self._use_hermes_backend() and not self._hermes_online:
            self._refresh_hermes_health()
            self._chat.append_message_instant(
                "Iris",
                "Hermes gateway에 연결할 수 없습니다. `hermes gateway` 실행과 API 서버 설정을 확인해 주세요.",
            )
            return

        self._chat.append_message_instant("You", text)
        self._history.append({"role": "user", "content": text})
        self._busy = True
        self._state.set_state(AppState.PROCESSING)

        if self._use_hermes_backend():
            worker = HermesChatWorker(
                self._settings.hermes_base_url,
                model,
                list(self._history),
                api_key=self._settings.hermes_api_key,
                command=self._settings.hermes_command,
                parent=self,
            )
            self._chat_worker = worker
            worker.connecting.connect(self._on_chat_connecting)
            worker.tool_progress.connect(self._on_hermes_tool_progress)
            worker.content_chunk.connect(self._on_content_chunk)
            worker.finished_ok.connect(self._on_chat_finished)
            worker.failed.connect(self._on_chat_failed)
            worker.start()
            return

        worker = OllamaChatWorker(
            self._settings.ollama_base_url,
            model,
            list(self._history),
            think=True,
            parent=self,
        )
        self._chat_worker = worker
        worker.connecting.connect(self._on_chat_connecting)
        worker.thinking_started.connect(self._on_thinking_started)
        worker.thinking_chunk.connect(self._on_thinking_chunk)
        worker.thinking_done.connect(self._on_thinking_done)
        worker.content_chunk.connect(self._on_content_chunk)
        worker.finished_ok.connect(self._on_chat_finished)
        worker.failed.connect(self._on_chat_failed)
        worker.start()

    def _on_hermes_tool_progress(self, message: str) -> None:
        text = (message or "").strip()
        if text:
            self._live_activity.append_instant_line(f"[tool] {text}")

    def _on_chat_connecting(self, model: str, host: str) -> None:
        backend = self._backend_label()
        self._live_activity.append_instant_line(
            f"Connecting to '{model}' via {backend} on '{host}' ⚡"
        )
        # 방금 보낸 사용자 메시지
        if self._history:
            last = self._history[-1]
            if last.get("role") == "user":
                self._live_activity.append_instant_line(f">>> {last.get('content', '')}")

    def _on_thinking_started(self) -> None:
        self._live_activity.append_instant_line("Thinking...")

    def _on_thinking_chunk(self, chunk: str) -> None:
        self._live_activity.append_instant_chunk(chunk)

    def _on_thinking_done(self) -> None:
        self._live_activity.append_instant_line("")
        self._live_activity.append_instant_line("...done thinking.")
        self._live_activity.append_instant_line("")
        self._state.set_state(AppState.RESPONDING)
        self._chat.begin_stream_message("Iris", speech_sync=False)

    def _on_content_chunk(self, chunk: str) -> None:
        if not getattr(self._chat, "_stream_active", False):
            # thinking 없이 content만 오는 모델
            self._state.set_state(AppState.RESPONDING)
            self._chat.begin_stream_message("Iris", speech_sync=False)
        self._chat.append_stream_chunk(chunk)

    def _on_chat_finished(self, content: str) -> None:
        text = (content or "").strip()
        if getattr(self._chat, "_stream_active", False):
            self._chat.end_stream_message(text or None)
        elif text:
            self._chat.append_message("Iris", text)
        else:
            self._chat.append_message_instant("Iris", "(빈 응답)")
        if text:
            self._history.append({"role": "assistant", "content": text})
        self._busy = False
        self._chat_worker = None
        self._state.set_state(AppState.IDLE)

    def _on_chat_failed(self, err: str) -> None:
        if getattr(self._chat, "_stream_active", False):
            self._chat.end_stream_message(None)
        # 실패한 user turn은 히스토리에서 제거 (재시도 깔끔하게)
        if self._history and self._history[-1].get("role") == "user":
            self._history.pop()
        self._live_activity.append_instant_line(f"Error: {err}")
        self._chat.append_message_instant(
            "Iris",
            f"{self._backend_label()} 오류: {err}",
        )
        self._busy = False
        self._chat_worker = None
        self._state.set_state(AppState.ERROR)
        QTimer.singleShot(800, lambda: self._state.set_state(AppState.IDLE))

    def _on_app_state(self, state: object) -> None:
        if isinstance(state, AppState):
            self._status_header.set_app_state(state)
            self._viz.set_state(state)

    def _on_metrics_snapshot(self, snapshot: object) -> None:
        self._left_sidebar.utility.metrics.apply_snapshot(snapshot)

    def _set_workspace_icon_active(self, action_id: str | None) -> None:
        actions = self._left_sidebar.utility.actions
        for aid in actions._buttons:
            actions.set_action_active(aid, aid == action_id)

    def _show_assistant_workspace(self) -> None:
        self._workspace_mode = "assistant"
        self._workspace_stack.setCurrentWidget(self._assistant_page)
        self._left_sidebar.set_workspace_mode("assistant")
        self._set_workspace_icon_active(None)
        self._viz.show()
        self._orb_spacer.show()

    def _on_obsidian_icon(self) -> None:
        self._workspace_mode = "obsidian"
        self._workspace_stack.setCurrentWidget(self._obsidian_page)
        self._left_sidebar.set_workspace_mode("obsidian")
        self._set_workspace_icon_active("obsidian")
        self._viz.hide()
        self._orb_spacer.hide()
        self._left_sidebar.obsidian_detail.reload()
        if self._obsidian_page.current_note:
            self._obsidian_page.show_note(self._obsidian_page.current_note)

    def _on_email_icon(self) -> None:
        self._workspace_mode = "email"
        self._workspace_stack.setCurrentWidget(self._email_page)
        self._left_sidebar.set_workspace_mode("email")
        self._set_workspace_icon_active("email")
        self._viz.hide()
        self._orb_spacer.hide()
        accounts = load_email_accounts(self._db)
        self._email_page.set_accounts(accounts, selected_id=self._selected_email_account_id)
        if accounts:
            self._refresh_email_inbox()
        else:
            self._left_sidebar.email_detail.set_status("프로필에서 이메일 계정을 추가하세요.")

    def _on_email_account_changed(self, account_id: str) -> None:
        self._selected_email_account_id = account_id
        self._refresh_email_inbox()

    def _refresh_email_inbox(self) -> None:
        account = self._email_page.current_account()
        if not account:
            return
        if self._email_inbox_worker is not None and self._email_inbox_worker.isRunning():
            return
        self._email_page.set_loading(True)
        self._left_sidebar.email_detail.clear_mails()
        worker = EmailInboxWorker(account, parent=self)
        self._email_inbox_worker = worker
        worker.finished_ok.connect(self._on_email_inbox_loaded)
        worker.failed.connect(self._on_email_inbox_failed)
        worker.start()

    def _on_email_inbox_loaded(self, items: object) -> None:
        from iris.infrastructure.email_client import MailSummary

        mails: list[MailSummary] = list(items) if isinstance(items, list) else []
        self._email_inbox_worker = None
        self._email_page.set_loading(False)
        self._left_sidebar.email_detail.set_mails(mails)
        if mails:
            self._load_email_message(mails[0].uid)
        else:
            self._email_page.show_empty_inbox_hint()

    def _on_email_inbox_failed(self, err: str) -> None:
        self._email_inbox_worker = None
        self._email_page.set_loading(False)
        self._left_sidebar.email_detail.set_status("불러오기 실패")
        self._email_page.show_error(f"받은편함 오류: {err[:200]}")

    def _load_email_message(self, uid: str) -> None:
        account = self._email_page.current_account()
        if not account or not uid:
            return
        if self._email_message_worker is not None and self._email_message_worker.isRunning():
            return
        worker = EmailMessageWorker(account, uid, parent=self)
        self._email_message_worker = worker
        worker.finished_ok.connect(self._on_email_message_loaded)
        worker.failed.connect(self._on_email_message_failed)
        worker.start()

    def _on_email_message_loaded(self, msg: object) -> None:
        from iris.infrastructure.email_client import MailMessage

        self._email_message_worker = None
        if isinstance(msg, MailMessage):
            self._email_page.show_message(msg)

    def _on_email_message_failed(self, err: str) -> None:
        self._email_message_worker = None
        self._email_page.show_error(f"본문 오류: {err[:200]}")

    def _send_email(self, to: str, subject: str, body: str) -> None:
        account = self._email_page.current_account()
        if not account:
            return
        if self._email_send_worker is not None and self._email_send_worker.isRunning():
            return
        self._email_page.set_loading(True)
        worker = EmailSendWorker(account, to, subject, body, parent=self)
        self._email_send_worker = worker
        worker.finished_ok.connect(self._on_email_sent)
        worker.failed.connect(self._on_email_send_failed)
        worker.start()

    def _on_email_sent(self) -> None:
        self._email_send_worker = None
        self._email_page.set_loading(False)
        self._live_activity.append_instant_line("Email sent.")
        self._refresh_email_inbox()

    def _on_email_send_failed(self, err: str) -> None:
        self._email_send_worker = None
        self._email_page.set_loading(False)
        self._email_page.show_error(f"발송 실패: {err[:200]}")

    def _on_mobile_icon(self) -> None:
        if is_emulator_running():
            self._live_activity.append_instant_line("Android 에뮬레이터가 이미 실행 중입니다.")
            return
        try:
            proc = launch_emulator()
            self._live_activity.append_instant_line(
                f"Android 에뮬레이터 시작 (PID {proc.pid}) — android-emulator/data"
            )
        except OSError as exc:
            self._live_activity.append_instant_line(f"에뮬레이터 시작 실패: {exc}")
            self._notes.try_add_alert(
                target_id=0,
                category="ERROR",
                title="Android 에뮬레이터",
                message=str(exc),
                focus_hint="",
                event_id=0,
            )

    def _open_user_profile_dialog(self) -> None:
        dlg = UserProfileDialog(self._db, self)
        if dlg.exec() and self._workspace_mode == "email":
            accounts = load_email_accounts(self._db)
            self._email_page.set_accounts(accounts, selected_id=self._selected_email_account_id)
            if accounts:
                self._refresh_email_inbox()

    def _open_settings_dialog(self) -> None:
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec():
            sel = dlg.selection()
            if sel is None:
                return
            self._settings.ollama_base_url = sel.ollama_base_url
            self._settings.ollama_model = sel.ollama_model
            self._settings.hermes_enabled = sel.hermes_enabled
            self._settings.hermes_command = sel.hermes_command
            self._settings.hermes_base_url = sel.hermes_base_url
            self._settings.hermes_api_key = sel.hermes_api_key
            self._settings.model_name = sel.ollama_model or self._settings.model_name
            self._saved_model = sel.ollama_model.strip()
            if self._saved_model:
                save_selected_model(self._db, self._saved_model)
            self._status_header.set_model_name(self._settings.model_name or "(unset)")
            self._refresh_hermes_health()
            if self._settings.hermes_enabled and self._saved_model:
                self._sync_hermes_model(self._saved_model)
            self._refresh_models()

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        suppress_native_window_border(self)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._drag.set_maximized(self.isMaximized())
            self._viz.request_sync_orb_anchor("window_state_change")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._viz.request_sync_orb_anchor("main_window_resize")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        try:
            if self._chat_worker is not None and self._chat_worker.isRunning():
                cancel = getattr(self._chat_worker, "request_cancel", None)
                if callable(cancel):
                    cancel()
                self._chat_worker.wait(1500)
            self._metrics_worker.request_stop()
            self._metrics_worker.wait(2000)
        except Exception:
            pass
        super().closeEvent(event)
