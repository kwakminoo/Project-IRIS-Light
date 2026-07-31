"""메인 PyQt6 창 — Ollama 모델 선택 + Hermes/Ollama 채팅."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from PyQt6.QtCore import QEvent, QRect, Qt, QThread, QTimer
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtMultimedia import QSoundEffect
import tempfile

from iris.audio.recorder import AudioRecorder, RecordingResult
from iris.audio.text_normalizer import load_pronunciation_map, split_tts_sentences
from iris.audio.voice_runtime_manager import VoiceRuntimeProcessManager
from iris.audio.workers import STTTranscriptionWorker, TTSSynthesisWorker
from iris.config.settings import load_settings
from iris.core.activity_sink import register_activity_sink
from iris.core.state_machine import AppState, StateMachine
from iris.infrastructure.ollama_client import OllamaModelInfo
from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.email_accounts import EmailAccount, find_account, load_email_accounts
from iris.monitoring.notification_policy import NotificationPolicy
from iris.storage.database import Database
from iris.storage.model_prefs import load_selected_model, save_selected_model
from iris.storage.user_profile import load_user_profile, save_user_profile
from iris.storage.voice_prefs import VoicePreferences, load_voice_preferences, save_voice_preferences
from iris.system.android_emulator import (
    is_emulator_headless,
    is_emulator_running,
    launch_emulator,
    restart_emulator_windowed,
)
from iris.system.api_quota_worker import ApiQuotaWorker
from iris.system.ide_launcher import (
    get_ide_spec,
    launch_ide,
    list_ide_windows,
    open_folder_in_ide,
    resolve_ide_exe,
    wait_for_new_ide_window,
)
from iris.system.ide_tiler import compute_tile_rects, tile_ide_and_iris, work_area_for
from iris.system.metrics_worker import MetricsWorker
from iris.ui.chat_panel import ChatPanel
from iris.ui.context_ring import estimate_messages_tokens
from iris.ui.cyberspace_background import CyberspaceBackground
from iris.ui.cyberspace_theme import apply_cyberspace_theme
from iris.ui.drag_tab import DragTab
from iris.ui.frameless_chrome import FramelessShell, center_on_screen, suppress_native_window_border
from iris.ui.left_sidebar_panel import LeftSidebarPanel
from iris.ui.live_activity_panel import LiveActivityPanel, UiActivityRelay
from iris.ui.notification_panel import NotificationPanel
from iris.ui.boot_checks_worker import BootChecksWorker
from iris.ui.control_bindings import (
    mark_control_ready,
    start_control_surface,
    stop_control_surface,
)
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
from iris.ui.ide_icons import show_ide_not_installed_dialog
from iris.ui.visualizer import Visualizer
from iris.ui.workspaces.assistant_workspace_page import AssistantWorkspacePage
from iris.ui.workspaces.email_workspace_page import EmailWorkspacePage
from iris.ui.workspaces.ide_companion_page import (
    EMAIL_ORB_HEIGHT,
    EMAIL_ORB_SCALE,
    IdeCompanionPage,
)
from iris.ui.workspaces.obsidian_workspace_page import ObsidianWorkspacePage


@dataclass
class IdeSession:
    active: bool = False
    ide_id: str = ""
    hwnd: int | None = None
    pid: int | None = None
    workspace_root: str = ""
    mode: str = "welcome"  # "welcome" | "workspace"
    source: str = "icon"  # "icon" | "chat"
    last_seen_at: float = 0.0


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
        self._voice_prefs: VoicePreferences = load_voice_preferences(self._db)
        self._history: list[dict[str, str]] = []
        self._last_assistant_text = ""
        self._chat_worker: QThread | None = None
        self._stt_worker: STTTranscriptionWorker | None = None
        self._tts_worker: TTSSynthesisWorker | None = None
        self._model_worker: OllamaModelListWorker | None = None
        self._hermes_health_worker: HermesHealthWorker | None = None
        self._hermes_model_worker: HermesModelSyncWorker | None = None
        self._email_inbox_worker: EmailInboxWorker | None = None
        self._email_message_worker: EmailMessageWorker | None = None
        self._email_send_worker: EmailSendWorker | None = None
        self._email_chat_worker: HermesChatWorker | None = None
        self._email_history: list[dict[str, str]] = []
        self._email_busy = False
        self._boot_checks_worker: BootChecksWorker | None = None
        self._boot_checks_done = False
        self._email_preloaded = False
        self._tts_queue: list[str] = []
        self._tts_active_msg_id: str = ""
        self._email_view: tuple[str, str] = ("inbox", "")  # (folder_key, gmail_category)
        self._email_folder = "inbox"  # 메시지 조회용 메일함 키
        self._selected_email_account_id = ""
        self._hermes_online = False
        self._busy = False
        self._workspace_mode = "assistant"
        self._ui_mode = "normal"  # "normal" | "ide_companion"
        self._ide_hwnd: int | None = None
        self._ide_pid: int | None = None
        self._ide_session = IdeSession()
        self._ide_session_watch = QTimer(self)
        self._ide_session_watch.setInterval(2000)
        self._ide_session_watch.timeout.connect(self._refresh_ide_session_state)
        self._ide_session_watch.start()
        self._companion_saved_sizes: list[int] | None = None
        self._companion_saved_assistant_sizes: list[int] | None = None
        self._companion_saved_geometry = None
        self._companion_saved_min_size = None
        self._orb_spacer_min_h = 160
        self._normal_root_margins = (
            TOKENS.spacing_lg,
            TOKENS.spacing_sm,
            TOKENS.spacing_lg,
            TOKENS.spacing_sm,
        )
        self._intro: StartupIntroAnimator | None = None
        self._control_surface = None
        self._saved_model = load_selected_model(self._db) or self._settings.ollama_model.strip()
        if self._saved_model:
            self._settings.ollama_model = self._saved_model
            self._settings.model_name = self._saved_model
        self._voice_runtime = VoiceRuntimeProcessManager(
            base_url=self._voice_prefs.voice_runtime_url,
            iris_root=Path(__file__).resolve().parents[2],
        )
        self._mic_listen_active = False
        # ponytail: STT QThread는 중단이 약함 — 끄기 시 세션만 올리면 늦은 콜백 무시
        self._stt_session = 0
        self._recorder = AudioRecorder(self)
        self._recorder.level_changed.connect(self._on_recorder_level)
        self._recorder.recording_started.connect(self._on_recording_started)
        self._recorder.recording_stopped.connect(self._on_recording_stopped)
        self._recorder.recording_cancelled.connect(self._on_recording_cancelled)
        self._recorder.utterance_ready.connect(self._on_utterance_ready)
        self._recorder.failed.connect(self._on_recording_failed)
        self._tts_player = QSoundEffect(self)
        self._tts_player.playingChanged.connect(self._on_tts_playing_changed)

        central = CyberspaceBackground()
        self._cyberspace_bg = central
        self._viz = Visualizer(central)

        ui_overlay = QWidget()
        ui_overlay.setObjectName("UiOverlay")
        self._ui_overlay = ui_overlay
        central.set_orb_layer(self._viz)
        central.set_ui_overlay(ui_overlay)

        root = QVBoxLayout(ui_overlay)
        root.setContentsMargins(*self._normal_root_margins)
        root.setSpacing(TOKENS.spacing_sm)
        self._root_lay = root

        self._drag = DragTab(self)
        self._drag.profile_clicked.connect(self._open_user_profile_dialog)
        self._drag.settings_clicked.connect(self._open_settings_dialog)
        self._drag.ide_toggle_clicked.connect(self._on_ide_icon)
        self._drag.minimize_clicked.connect(self.showMinimized)
        self._drag.maximize_clicked.connect(self._toggle_maximize)
        self._drag.mic_clicked.connect(self._on_chat_mic_clicked)
        root.addWidget(self._drag)

        status_header = TopStatusHeader()
        self._status_header = status_header
        status_header.set_model_name(
            self._settings.model_name or self._settings.ollama_model or "(unset)"
        )
        status_header.set_tts_status("OFF")
        status_header.set_app_state(AppState.IDLE)
        self._drag.place_status_rows(
            status_header.status_widget(),
            status_header.backend_row(),
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(0)
        self._main_splitter = splitter

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

        self._companion_page = IdeCompanionPage()
        self._body_stack = QStackedWidget()
        self._body_stack.setObjectName("MainBodyStack")
        self._body_stack.addWidget(splitter)
        self._body_stack.addWidget(self._companion_page)

        self._iris_wiki = IrisWiki(Path(__file__).resolve().parents[2] / "obsidian-vault")
        self._obsidian_page.set_wiki(self._iris_wiki)
        self._left_sidebar.obsidian_detail.set_wiki(self._iris_wiki)
        self._left_sidebar.obsidian_detail.note_selected.connect(self._obsidian_page.show_note)
        self._email_page.refresh_requested.connect(self._refresh_email_inbox)
        self._email_page.compose_requested.connect(self._send_email)
        self._email_page.mail_selected.connect(self._load_email_message)
        self._email_page.email_chat_send.connect(self._on_email_chat_send)
        self._email_page.category_selected.connect(self._on_email_category)
        self._left_sidebar.email_folder.account_changed.connect(self._on_email_account_changed)
        self._left_sidebar.email_folder.compose_requested.connect(self._open_email_compose)
        self._left_sidebar.email_folder.folder_selected.connect(self._on_email_folder_selected)

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
            self._companion_page,
            ui_overlay,
            central,
            self,
        )

        self._activity_relay = UiActivityRelay(self)
        self._live_activity = LiveActivityPanel(self)
        self._activity_relay.line.connect(self._live_activity.enqueue_typed_line)
        register_activity_sink(self._activity_relay.push)
        left_lay.addWidget(self._live_activity, 0)
        # Hermes health/MCP sync는 control surface 기동 이후에 (아래 start 이후)

        self._chat = ChatPanel()
        self._settings.always_listen_speech_rms = self._voice_prefs.stt_speech_rms
        self._chat.set_speech_threshold_rms(self._voice_prefs.stt_speech_rms)
        self._chat.send_clicked.connect(self._on_user_text)
        self._chat.model_changed.connect(self._on_model_changed)
        self._chat.files_attached.connect(self._on_composer_files)
        self._chat.skill_inserted.connect(self._on_composer_skill)
        self._chat.mcp_inserted.connect(self._on_composer_mcp)
        self._chat.mic_clicked.connect(self._on_chat_mic_clicked)
        self._chat.speaker_clicked.connect(self._on_chat_speaker_clicked)
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
            ("ide", "ide", "IDE Companion"),
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
            elif action_id == "ide":
                callback = self._on_ide_icon
            actions.add_icon_action(
                action_id=action_id,
                icon_kind=icon_kind,
                tooltip=tooltip,
                callback=callback,
            )

        self._metrics_worker = MetricsWorker(parent=self)
        self._metrics_worker.snapshot_ready.connect(self._on_metrics_snapshot)
        self._api_quota_worker = ApiQuotaWorker(parent=self)
        self._api_quota_worker.quotas_ready.connect(self._on_api_quotas)
        if not self._test_mode:
            self._metrics_worker.start()
            self._api_quota_worker.start()

        root.addWidget(self._body_stack, 1)

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
            start_control_surface(self)
            # control이 뜬 뒤 MCP 동기화·gateway 점검 (백그라운드 워커)
            self._refresh_hermes_health()
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
        mark_control_ready(self)
        self._chat.append_message("Iris", self._ready_status_message())
        QTimer.singleShot(200, self._seed_demo_alert)

    def _seed_demo_alert(self) -> None:
        self._notes.try_add_alert(
            target_id=0,
            category="NORMAL",
            title="Iris Light",
            message="Ollama 모델 목록이 연결되었습니다. Hermes gateway는 자동으로 기동됩니다.",
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
        worker.notice.connect(self._on_hermes_gateway_notice)
        worker.finished_ok.connect(self._on_hermes_health)
        worker.failed.connect(self._on_hermes_health_failed)
        worker.start()

    def _on_hermes_gateway_notice(self, message: str) -> None:
        text = (message or "").strip()
        panel = getattr(self, "_live_activity", None)
        if text and panel is not None:
            panel.append_instant_line(text)

    def _on_hermes_health(self, online: object) -> None:
        self._hermes_online = bool(online)
        self._status_header.refresh_backend_status(
            self._settings,
            hermes_online=self._hermes_online,
        )
        if self._hermes_online:
            model = (
                self._chat.current_model()
                or self._saved_model
                or self._settings.ollama_model
            ).strip()
            if model:
                self._sync_hermes_model(model)
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
        self._chat.set_model_status("(클라우드 모델 확인 중…)")
        worker = OllamaModelListWorker(self._settings.ollama_base_url, parent=self)
        self._model_worker = worker
        worker.notice.connect(self._live_activity.append_instant_line)
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
            n_cloud = sum(1 for m in items if getattr(m, "is_cloud", False))
            n_local = len(items) - n_cloud
            self._live_activity.append_instant_line(
                f"Models: {n_local} local + {n_cloud} cloud"
            )
            if self._settings.hermes_enabled and chosen:
                self._sync_hermes_model(chosen)
        else:
            self._chat.set_model_status("(클라우드 모델 없음)")
        if self._intro is not None:
            self._intro.notify_models_ready()
        self._start_boot_checks()

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
        self._start_boot_checks()

    def _start_boot_checks(self) -> None:
        """모델·서버 확인 뒤 Wiki·이메일·에뮬레이터를 순차 점검(1회)."""
        if self._boot_checks_done or self._test_mode:
            return
        if self._boot_checks_worker is not None and self._boot_checks_worker.isRunning():
            return
        self._boot_checks_done = True
        accounts = load_email_accounts(self._db)
        account = accounts[0] if accounts else None
        worker = BootChecksWorker(self._iris_wiki, account, parent=self)
        self._boot_checks_worker = worker
        worker.progress.connect(self._on_boot_check_progress)
        worker.inbox_ready.connect(self._on_boot_inbox_ready)
        worker.finished_ok.connect(self._on_boot_checks_done)
        worker.start()

    def _on_boot_check_progress(self, message: str) -> None:
        """각 상태 확인 결과를 개별 알림으로 표시(순차 방출 → 하나씩)."""
        text = (message or "").strip()
        if not text:
            return
        category = "ERROR_DETECTED" if "실패" in text else "NORMAL"
        self._notes.try_add_alert(
            target_id=0,
            category=category,
            title="상태 확인",
            message=text,
            focus_hint="",
            event_id=0,
        )

    def _on_boot_inbox_ready(self, items: object) -> None:
        """부팅 점검 중 미리 불러온 받은편지함을 이메일 화면에 채워둔다."""
        from iris.infrastructure.email_client import MailSummary

        mails: list[MailSummary] = list(items) if isinstance(items, list) else []
        self._email_page.set_current_account(self._current_email_account())
        self._email_page.set_mails(mails)
        self._email_preloaded = True

    def _on_boot_checks_done(self) -> None:
        self._boot_checks_worker = None

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
            from iris.infrastructure.model_descriptions import describe_model

            desc = describe_model(model)
            if desc:
                self._live_activity.append_instant_line(f"모델: {desc}")
        if self._settings.hermes_enabled:
            self._sync_hermes_model(model)
        self._refresh_context_gauge()

    def _refresh_context_gauge(self) -> None:
        """선택 모델 컨텍스트 한도 + 현재 대화 추정 토큰으로 원형 게이지 갱신."""
        model = self._chat.current_model()
        if not model:
            self._chat.set_context_usage(0, 128_000)
            return
        cache = getattr(self, "_context_limit_cache", None)
        if cache is None:
            self._context_limit_cache = {}
            cache = self._context_limit_cache
        limit = cache.get(model)
        if limit is None:
            try:
                from iris.infrastructure.ollama_client import OllamaClient

                client = OllamaClient(self._settings.ollama_base_url)
                limit = client.model_context_length(model)
            except Exception:
                limit = 128_000
            cache[model] = limit
        used = estimate_messages_tokens(self._history)
        self._chat.set_context_usage(used, limit)

    def _use_hermes_backend(self) -> bool:
        return bool(self._settings.hermes_enabled)

    def _backend_label(self) -> str:
        return "Hermes" if self._use_hermes_backend() else "Ollama"

    def _on_composer_files(self, paths: object) -> None:
        items = [str(p) for p in (paths or []) if str(p).strip()]
        if not items:
            return
        self._live_activity.append_instant_line(f"Attached {len(items)} file(s)")

    def _on_composer_skill(self, name: str) -> None:
        text = (name or "").strip()
        if text:
            self._live_activity.append_instant_line(f"Skill: /{text}")

    def _on_composer_mcp(self, name: str) -> None:
        text = (name or "").strip()
        if text:
            self._live_activity.append_instant_line(f"MCP: {text}")

    def _on_user_text(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self._busy:
            self._live_activity.append_instant_line("Busy — wait for the current reply.")
            return
        # IDE 아이콘과 동일 동작 — 모델이 도구를 안 써도 Companion이 켜지게
        if self._try_local_ide_control(text):
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
            self._live_activity.append_instant_line(
                "Hermes gateway Offline — 기동 후 연결을 시도합니다…"
            )
            self._refresh_hermes_health()

        self._chat.append_message_instant("You", text)
        self._history.append({"role": "user", "content": text})
        self._refresh_context_gauge()
        self._busy = True
        self._state.set_state(AppState.PROCESSING)

        if self._use_hermes_backend():
            messages = self._chat_messages_with_project_context()
            worker = HermesChatWorker(
                self._settings.hermes_base_url,
                model,
                messages,
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
            self._chat_messages_with_project_context(),
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
            f"Connecting to '{model}' via {backend} on '{host}'"
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
            self._last_assistant_text = text
        self._refresh_context_gauge()
        if self._use_hermes_backend() and not self._hermes_online:
            self._hermes_online = True
            self._status_header.refresh_backend_status(
                self._settings,
                hermes_online=True,
            )
        self._busy = False
        self._chat_worker = None
        self._state.set_state(AppState.IDLE)
        if text and self._voice_prefs.tts_enabled and self._voice_prefs.tts_mode == "auto":
            self._enqueue_tts(text, msg_id=self._chat._last_tts_id or "last")

    def _ensure_voice_runtime(self) -> bool:
        try:
            self._voice_runtime.set_base_url(self._voice_prefs.voice_runtime_url)
            status = self._voice_runtime.ensure_started(
                mock_mode=self._voice_prefs.voice_runtime_mock
            )
            self._status_header.set_tts_status("READY")
            return status.running
        except Exception as exc:  # noqa: BLE001
            self._status_header.set_tts_status("ERROR")
            self._live_activity.append_instant_line(
                f"Voice runtime 오류: {exc} (메인 앱은 계속 사용 가능)"
            )
            return False

    def _set_mic_recording(self, recording: bool) -> None:
        self._mic_listen_active = recording
        self._drag.set_mic_recording(recording)
        self._chat.set_mic_recording(recording)

    def _on_chat_mic_clicked(self) -> None:
        if self._mic_listen_active or self._recorder.is_continuous():
            self._stop_mic_listen()
            return
        if not self._voice_prefs.stt_enabled:
            self._live_activity.append_instant_line("STT가 비활성화되어 있어 기본 설정으로 시작합니다.")
            self._voice_prefs.stt_enabled = True
            save_voice_preferences(self._db, self._voice_prefs)
        if not self._ensure_voice_runtime():
            return
        self._chat.begin_user_listening()
        self._set_mic_recording(True)
        self._state.set_state(AppState.LISTENING)
        self._recorder.start_continuous(
            device_id=self._voice_prefs.stt_device_id,
            speech_rms=self._voice_prefs.stt_speech_rms,
            sample_rate=16000,
            channels=1,
        )

    def _stop_mic_listen(self) -> None:
        self._stt_session += 1
        self._set_mic_recording(False)
        self._chat.cancel_user_listening()
        self._recorder.set_capture_paused(False)
        if self._recorder.is_recording():
            self._recorder.cancel_recording()
        self._state.set_state(AppState.IDLE)

    def _on_recording_started(self) -> None:
        if self._mic_listen_active:
            self._chat.set_user_listening_status("듣고 있습니다")

    def _on_recorder_level(self, level: float) -> None:
        self._chat.set_mic_level(level)
        self._viz.set_mic_level(level)

    def _on_recording_stopped(self, result: RecordingResult) -> None:
        # oneshot 경로(레거시) — 연속 청취는 utterance_ready 사용
        self._transcribe_wav(result, keep_listening=False)

    def _on_utterance_ready(self, result: RecordingResult) -> None:
        if not self._mic_listen_active:
            return
        self._transcribe_wav(result, keep_listening=True)

    def _transcribe_wav(self, result: RecordingResult, *, keep_listening: bool) -> None:
        if keep_listening and not self._mic_listen_active:
            return
        if not result.wav_bytes:
            if not keep_listening:
                self._on_recording_failed("빈 녹음입니다.")
            return
        min_rms = max(0.001, self._voice_prefs.stt_speech_rms * 0.5)
        if result.duration_sec < 0.25 or result.rms_peak < min_rms:
            if not keep_listening:
                self._on_recording_failed("무음에 가깝습니다. 마이크와 거리를 확인해 주세요.")
            elif self._mic_listen_active:
                self._chat.set_user_listening_status("듣고 있습니다")
            return
        if self._stt_worker is not None and self._stt_worker.isRunning():
            return
        if keep_listening and not self._mic_listen_active:
            return
        self._recorder.set_capture_paused(True)
        self._chat.set_user_listening_status("음성을 인식하고 있습니다")
        if not keep_listening:
            self._state.set_state(AppState.PROCESSING)
        session = self._stt_session
        worker = STTTranscriptionWorker(
            result.wav_bytes,
            runtime_url=self._voice_prefs.voice_runtime_url,
            model_name=self._voice_prefs.stt_model,
            language=self._voice_prefs.stt_language,
            parent=self,
        )
        self._stt_worker = worker
        worker.finished_ok.connect(
            lambda payload, kl=keep_listening, s=session: self._on_stt_finished(
                payload, keep_listening=kl, session=s
            )
        )
        worker.failed.connect(
            lambda err, kl=keep_listening, s=session: self._on_stt_failed(
                err, keep_listening=kl, session=s
            )
        )
        worker.start()

    def _on_recording_cancelled(self) -> None:
        self._chat.cancel_user_listening()
        self._set_mic_recording(False)
        self._state.set_state(AppState.IDLE)

    def _on_recording_failed(self, err: str) -> None:
        self._chat.cancel_user_listening()
        self._set_mic_recording(False)
        if self._recorder.is_recording():
            self._recorder.cancel_recording()
        self._state.set_state(AppState.ERROR)
        self._live_activity.append_instant_line(f"녹음 오류: {err}")
        QTimer.singleShot(800, lambda: self._state.set_state(AppState.IDLE))

    def _on_stt_finished(
        self, payload: object, *, keep_listening: bool = False, session: int | None = None
    ) -> None:
        if session is not None and session != self._stt_session:
            self._stt_worker = None
            return
        self._stt_worker = None
        self._recorder.set_capture_paused(False)
        if keep_listening and not self._mic_listen_active:
            self._chat.cancel_user_listening()
            self._state.set_state(AppState.IDLE)
            return
        data = payload if isinstance(payload, dict) else {}
        text = str(data.get("text") or "").strip()
        if keep_listening and self._mic_listen_active:
            if text:
                self._chat.insert_input_text(text)
                self._live_activity.append_instant_line("STT 완료 — 입력창에 전사 결과를 넣었습니다.")
            self._chat.set_user_listening_status("듣고 있습니다")
            self._state.set_state(AppState.LISTENING)
            return
        self._set_mic_recording(False)
        self._chat.cancel_user_listening()
        if not text:
            self._chat.append_message_instant("Iris", "음성이 감지되지 않았습니다. 다시 시도해 주세요.")
            self._state.set_state(AppState.IDLE)
            return
        self._chat.insert_input_text(text)
        self._live_activity.append_instant_line("STT 완료 — 입력창에 전사 결과를 넣었습니다.")
        self._state.set_state(AppState.IDLE)

    def _on_stt_failed(
        self, err: str, *, keep_listening: bool = False, session: int | None = None
    ) -> None:
        if session is not None and session != self._stt_session:
            self._stt_worker = None
            return
        self._stt_worker = None
        self._recorder.set_capture_paused(False)
        if keep_listening and not self._mic_listen_active:
            self._chat.cancel_user_listening()
            self._state.set_state(AppState.IDLE)
            return
        if keep_listening and self._mic_listen_active:
            self._live_activity.append_instant_line(f"STT 오류: {err}")
            self._chat.set_user_listening_status("듣고 있습니다")
            self._state.set_state(AppState.LISTENING)
            return
        self._set_mic_recording(False)
        self._chat.cancel_user_listening()
        self._chat.append_message_instant("Iris", f"STT 오류: {err}")
        self._state.set_state(AppState.ERROR)
        QTimer.singleShot(800, lambda: self._state.set_state(AppState.IDLE))

    def _stop_tts_playback(self) -> None:
        self._tts_queue = []
        if self._tts_active_msg_id:
            self._chat.set_speaker_status(self._tts_active_msg_id, "idle")
        self._tts_active_msg_id = ""
        try:
            self._tts_player.stop()
        except Exception:
            pass
        if self._tts_worker is not None and self._tts_worker.isRunning():
            try:
                self._tts_worker.wait(500)
            except Exception:
                pass
        self._tts_worker = None
        self._status_header.set_tts_status("READY" if self._voice_prefs.tts_enabled else "OFF")

    def _on_chat_speaker_clicked(self, token: str) -> None:
        text = self._chat.get_tts_text(token)
        if not text and self._last_assistant_text:
            text = self._last_assistant_text
        if not text:
            self._live_activity.append_instant_line("재생할 답변이 없습니다.")
            return
        msg_id = token if token and token != "last" else (self._chat._last_tts_id or "last")
        self._enqueue_tts(text, msg_id=msg_id)

    def _enqueue_tts(self, text: str, *, msg_id: str = "last") -> None:
        mapping = load_pronunciation_map(self._voice_prefs.pronunciation_dict_json)
        from iris.audio.text_normalizer import normalize_tts_text

        cleaned = split_tts_sentences(normalize_tts_text(text, mapping))
        if not cleaned:
            return
        ref_audio = self._voice_prefs.tts_reference_audio
        ref_text = self._voice_prefs.tts_reference_text
        if not ref_audio or not ref_text:
            self._live_activity.append_instant_line("TTS 기준 음성이 아직 설정되지 않았습니다.")
            return
        if not Path(ref_audio).is_file():
            self._live_activity.append_instant_line(f"기준 음성 파일이 없습니다: {ref_audio}")
            self._chat.set_speaker_status(msg_id, "error")
            return
        if not self._ensure_voice_runtime():
            self._chat.set_speaker_status(msg_id, "error")
            return
        self._stop_tts_playback()
        self._tts_active_msg_id = msg_id
        self._chat.set_speaker_status(msg_id, "busy")
        self._tts_queue = cleaned
        self._start_next_tts_segment()

    def _start_next_tts_segment(self) -> None:
        if self._tts_worker is not None and self._tts_worker.isRunning():
            return
        if not self._tts_queue:
            if self._tts_active_msg_id:
                self._chat.set_speaker_status(self._tts_active_msg_id, "idle")
            self._status_header.set_tts_status("READY" if self._voice_prefs.tts_enabled else "OFF")
            return
        if not self._voice_prefs.tts_voice_prompt_hash:
            try:
                from iris.audio.voice_runtime_client import VoiceRuntimeClient

                client = VoiceRuntimeClient(base_url=self._voice_prefs.voice_runtime_url)
                voice_hash = client.voice_prepare(
                    ref_audio_path=self._voice_prefs.tts_reference_audio,
                    ref_text=self._voice_prefs.tts_reference_text,
                    tts_model_name=self._voice_prefs.tts_model,
                    voice_prompt_hash=None,
                )
                self._voice_prefs.tts_voice_prompt_hash = voice_hash
                save_voice_preferences(self._db, self._voice_prefs)
            except Exception as exc:  # noqa: BLE001
                self._status_header.set_tts_status("ERROR")
                if self._tts_active_msg_id:
                    self._chat.set_speaker_status(self._tts_active_msg_id, "error")
                self._live_activity.append_instant_line(f"TTS 준비 실패: {exc}")
                self._tts_queue = []
                return
        text = self._tts_queue.pop(0)
        self._status_header.set_tts_status("BUSY")
        if self._tts_active_msg_id:
            self._chat.set_speaker_status(self._tts_active_msg_id, "busy")
        worker = TTSSynthesisWorker(
            runtime_url=self._voice_prefs.voice_runtime_url,
            text=text,
            voice_prompt_hash=self._voice_prefs.tts_voice_prompt_hash,
            model_name=self._voice_prefs.tts_model,
            parent=self,
        )
        self._tts_worker = worker
        worker.finished_ok.connect(self._on_tts_finished)
        worker.failed.connect(self._on_tts_failed)
        worker.start()

    def _on_tts_finished(self, payload: object) -> None:
        self._tts_worker = None
        data = payload if isinstance(payload, dict) else {}
        audio_path = str(data.get("audio_path") or "").strip()
        if not audio_path:
            self._on_tts_failed("생성 파일 경로가 비어 있습니다.")
            return
        if not Path(audio_path).is_file():
            self._on_tts_failed(f"생성 파일이 없습니다: {audio_path}")
            return
        self._tts_player.setSource(QUrl.fromLocalFile(audio_path))
        self._tts_player.setVolume(max(0.0, min(1.0, self._voice_prefs.tts_volume)))
        if self._mic_listen_active:
            self._recorder.set_capture_paused(True)
        self._tts_player.play()
        self._status_header.set_tts_status("SPEAK")
        if self._tts_active_msg_id:
            self._chat.set_speaker_status(self._tts_active_msg_id, "playing")

    def _on_tts_failed(self, err: str) -> None:
        self._tts_worker = None
        self._tts_queue = []
        self._status_header.set_tts_status("ERROR")
        if self._tts_active_msg_id:
            self._chat.set_speaker_status(self._tts_active_msg_id, "error")
        self._live_activity.append_instant_line(f"TTS 오류: {err}")

    def _on_tts_playing_changed(self) -> None:
        if self._tts_player.isPlaying():
            return
        if self._tts_queue:
            self._start_next_tts_segment()
        else:
            if self._tts_active_msg_id:
                self._chat.set_speaker_status(self._tts_active_msg_id, "idle")
            self._status_header.set_tts_status("READY" if self._voice_prefs.tts_enabled else "OFF")
            if self._mic_listen_active and (self._stt_worker is None or not self._stt_worker.isRunning()):
                self._recorder.set_capture_paused(False)

    def _on_chat_failed(self, err: str) -> None:
        if getattr(self._chat, "_stream_active", False):
            self._chat.end_stream_message(None)
        # 실패한 user turn은 히스토리에서 제거 (재시도 깔끔하게)
        if self._history and self._history[-1].get("role") == "user":
            self._history.pop()
        self._refresh_context_gauge()
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

    def _on_api_quotas(self, quotas: object) -> None:
        self._left_sidebar.utility.metrics.apply_quotas(quotas)

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
        self._left_sidebar.email_folder.set_accounts(
            accounts, selected_id=self._selected_email_account_id
        )
        if accounts and not self._selected_email_account_id:
            self._selected_email_account_id = self._left_sidebar.email_folder.current_account_id()
        self._email_page.set_current_account(self._current_email_account())
        if accounts:
            # 부팅 때 미리 불러온 메일이 있으면 로딩 없이 즉시 표시.
            if self._email_preloaded:
                self._email_preloaded = False
            else:
                self._refresh_email_inbox()
        else:
            self._email_page.set_mails([])
            self._left_sidebar.email_folder.set_status("설정에서 이메일 계정을 추가하세요.")

    def _current_email_account(self) -> EmailAccount | None:
        acc_id = self._selected_email_account_id or self._left_sidebar.email_folder.current_account_id()
        if acc_id:
            found = find_account(self._db, acc_id)
            if found is not None:
                return found
        accounts = load_email_accounts(self._db)
        return accounts[0] if accounts else None

    def _on_email_account_changed(self, account_id: str) -> None:
        self._selected_email_account_id = account_id
        self._email_page.set_current_account(self._current_email_account())
        self._refresh_email_inbox()

    def _on_email_folder_selected(self, name: str) -> None:
        from iris.ui.knowledge.email_detail_panel import FOLDER_KEYS

        key = FOLDER_KEYS.get(name, "inbox")
        self._email_page.set_category_index(0)  # 폴더 전환 시 카테고리 탭 초기화
        self._load_email_view(folder=key)

    def _on_email_category(self, index: int) -> None:
        from iris.infrastructure.email_client import GMAIL_CATEGORIES, is_gmail

        account = self._current_email_account()
        if not account:
            return
        if not is_gmail(account.address):
            if index == 0:
                self._load_email_view(folder="inbox")
            else:
                self._email_page.set_status_text(
                    "카테고리 분류는 Gmail 계정에서만 지원됩니다."
                )
            return
        self._load_email_view(category=GMAIL_CATEGORIES[index])

    def _load_email_view(self, *, folder: str = "inbox", category: str = "") -> None:
        account = self._current_email_account()
        if not account:
            return
        self._email_view = (folder, category)
        # 카테고리는 받은편지함 내부이므로 메시지 조회는 inbox 기준.
        self._email_folder = "inbox" if category else folder
        self._email_page.set_current_account(account)
        if self._email_inbox_worker is not None and self._email_inbox_worker.isRunning():
            return
        self._email_page.set_loading(True)
        worker = EmailInboxWorker(account, folder=folder, category=category, parent=self)
        self._email_inbox_worker = worker
        worker.finished_ok.connect(self._on_email_inbox_loaded)
        worker.failed.connect(self._on_email_inbox_failed)
        worker.start()

    def _refresh_email_inbox(self) -> None:
        folder, category = self._email_view
        self._load_email_view(folder=folder, category=category)

    def _on_email_inbox_loaded(self, items: object) -> None:
        from iris.infrastructure.email_client import MailSummary

        mails: list[MailSummary] = list(items) if isinstance(items, list) else []
        self._email_inbox_worker = None
        self._email_page.set_loading(False)
        self._email_page.set_mails(mails)

    def _on_email_inbox_failed(self, err: str) -> None:
        self._email_inbox_worker = None
        self._email_page.set_loading(False)
        self._left_sidebar.email_folder.set_status("불러오기 실패")
        self._email_page.show_error(f"받은편함 오류: {err[:200]}")

    def _load_email_message(self, uid: str) -> None:
        account = self._current_email_account()
        if not account or not uid:
            return
        if self._email_message_worker is not None and self._email_message_worker.isRunning():
            return
        worker = EmailMessageWorker(account, uid, folder=self._email_folder, parent=self)
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

    def _open_email_compose(self) -> None:
        account = self._current_email_account()
        if not account:
            self._left_sidebar.email_folder.set_status("먼저 이메일 계정을 추가하세요.")
            return
        self._email_page.open_compose(account)

    def _send_email(self, to: str, subject: str, body: str) -> None:
        account = self._current_email_account()
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

    # ---- 이메일 전용 아이리스 챗 → Hermes 에이전트 ----
    def _on_email_chat_send(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        panel = self._email_page.iris_panel
        if self._email_busy:
            panel.append_iris_error("이전 요청을 처리 중입니다. 잠시만요.")
            return
        if not self._settings.hermes_enabled:
            panel.append_iris_error(
                "이메일 업무는 Hermes 에이전트가 필요합니다. 설정에서 Hermes를 켜 주세요."
            )
            return
        if not self._hermes_online:
            self._refresh_hermes_health()
            panel.append_iris_tool("Hermes gateway Offline — 기동 후 연결을 시도합니다…")
        model = self._chat.current_model()
        if not model:
            panel.append_iris_error("사용할 모델을 먼저 선택해 주세요.")
            self._refresh_models()
            return

        from iris.infrastructure.email_client import build_agent_context

        account = self._current_email_account()
        address = account.address if account else ""
        context = build_agent_context(address, self._email_page.current_message())

        panel.append_user(text)
        self._email_history.append({"role": "user", "content": text})
        messages = [{"role": "system", "content": context}, *self._email_history]

        self._email_busy = True
        panel.set_orb_state("PROCESSING")
        worker = HermesChatWorker(
            self._settings.hermes_base_url,
            model,
            messages,
            api_key=self._settings.hermes_api_key,
            command=self._settings.hermes_command,
            parent=self,
        )
        self._email_chat_worker = worker
        worker.tool_progress.connect(self._on_email_chat_tool)
        worker.content_chunk.connect(self._on_email_chat_chunk)
        worker.finished_ok.connect(self._on_email_chat_finished)
        worker.failed.connect(self._on_email_chat_failed)
        worker.start()

    def _on_email_chat_tool(self, message: str) -> None:
        text = (message or "").strip()
        if text:
            self._email_page.iris_panel.append_iris_tool(text)
            self._email_page.iris_panel.set_orb_state("EXECUTING")

    def _on_email_chat_chunk(self, chunk: str) -> None:
        self._email_page.iris_panel.set_orb_state("RESPONDING")
        self._email_page.iris_panel.append_iris_chunk(chunk)

    def _on_email_chat_finished(self, content: str) -> None:
        text = (content or "").strip()
        self._email_page.iris_panel.end_iris()
        if text:
            self._email_history.append({"role": "assistant", "content": text})
        if not self._hermes_online:
            self._hermes_online = True
            self._status_header.refresh_backend_status(
                self._settings,
                hermes_online=True,
            )
        self._email_busy = False
        self._email_chat_worker = None
        self._email_page.iris_panel.set_orb_state("IDLE")

    def _on_email_chat_failed(self, err: str) -> None:
        self._email_page.iris_panel.end_iris()
        if self._email_history and self._email_history[-1].get("role") == "user":
            self._email_history.pop()
        self._email_page.iris_panel.append_iris_error(f"Hermes 오류: {err[:200]}")
        self._email_busy = False
        self._email_chat_worker = None
        self._email_page.iris_panel.set_orb_state("ERROR")

    def _try_local_ide_control(self, text: str) -> bool:
        """짧은 IDE 켜기/끄기 요청은 아이콘과 같은 로컬 핸들러로 처리."""
        import re

        normalized = re.sub(r"\s+", " ", text.strip().lower())
        enter_patterns = (
            r"^(ide|아이디이|에디터|cursor|vscode)\s*(켜|열어|실행|시작)(줘|라|요)?[!?.]*$",
            r"^(open|start|launch)\s+(the\s+)?(ide|cursor|vscode|companion)[!?.]*$",
            r"^(companion|컴패니언|동반\s*모드)\s*(켜|열어|시작)(줘|라|요)?[!?.]*$",
            r"^ide\s*on[!?.]*$",
        )
        exit_patterns = (
            r"^(ide|companion|컴패니언|동반\s*모드)\s*(꺼|닫아|종료)(줘|라|요)?[!?.]*$",
            r"^(close|exit|stop)\s+(the\s+)?(ide|companion)[!?.]*$",
            r"^ide\s*off[!?.]*$",
        )
        for pat in enter_patterns:
            if re.match(pat, normalized, flags=re.IGNORECASE):
                self._chat.append_message_instant("You", text)
                self._history.append({"role": "user", "content": text})
                if self._ui_mode == "ide_companion":
                    reply = "이미 IDE Companion 모드입니다."
                else:
                    self._enter_ide_companion()
                    reply = "IDE Companion을 켰습니다. (사이드바 IDE 아이콘과 동일)"
                self._chat.append_message_instant("Iris", reply)
                self._history.append({"role": "assistant", "content": reply})
                self._refresh_context_gauge()
                return True
        for pat in exit_patterns:
            if re.match(pat, normalized, flags=re.IGNORECASE):
                self._chat.append_message_instant("You", text)
                self._history.append({"role": "user", "content": text})
                if self._ui_mode != "ide_companion":
                    reply = "지금은 Companion 모드가 아닙니다."
                else:
                    self._exit_ide_companion()
                    reply = "IDE Companion을 종료했습니다."
                self._chat.append_message_instant("Iris", reply)
                self._history.append({"role": "assistant", "content": reply})
                self._refresh_context_gauge()
                return True
        return False

    def _chat_messages_with_project_context(self) -> list[dict[str, str]]:
        """Hermes/Ollama 요청용 — Iris Control MCP 지침 + project_root."""
        messages = list(self._history)
        try:
            profile = load_user_profile(self._db)
            root = (profile.project_root or "").strip()
        except Exception:
            root = ""
        bits = [
            "Iris Light UI control: for IDE / Companion / open project / 작업 시작, "
            "use MCP tools iris_get_state / iris_get_catalog / iris_invoke "
            "(e.g. iris_invoke action=ide.enter_companion). "
            "Do NOT use terminal cursor/code alone — that skips Companion tiling. "
            "Do NOT invent that Iris has no IDE — Iris controls the preferred IDE via MCP. "
            "Writing code: project.write_file with open=true (typewriter into visible IDE tab). "
            "Running code: project.run — output in IDE integrated terminal; summarize only in chat.",
        ]
        if root:
            bits.append(f"Project root: {root}")
            bits.append(
                "바이브코딩은 Iris 채팅으로 진행합니다. IDE 내장 AI를 대체하지 않습니다."
            )
        return [{"role": "system", "content": "\n".join(bits)}, *messages]

    def _on_ide_icon(self) -> None:
        if self._ui_mode == "ide_companion":
            self._exit_ide_companion()
            return
        self._enter_ide_companion(source="icon")

    def _ide_hwnd_alive(self, hwnd: int | None) -> bool:
        if not hwnd:
            return False
        try:
            import win32gui  # type: ignore

            return bool(win32gui.IsWindow(int(hwnd)))
        except Exception:
            return False

    def _current_preferred_ide(self) -> str:
        profile = load_user_profile(self._db)
        return (profile.preferred_ide or "cursor").strip().lower() or "cursor"

    def _current_project_root(self) -> str:
        try:
            profile = load_user_profile(self._db)
            root = (profile.project_root or "").strip()
            if root and Path(root).expanduser().is_dir():
                return str(Path(root).expanduser().resolve())
        except Exception:
            pass
        return ""

    def _bind_ide_session(
        self,
        *,
        ide_id: str,
        hwnd: int,
        pid: int | None,
        workspace_root: str,
        mode: str,
        source: str,
    ) -> None:
        root = ""
        if workspace_root:
            try:
                root = str(Path(workspace_root).expanduser().resolve())
            except OSError:
                root = ""
        self._ide_session = IdeSession(
            active=True,
            ide_id=(ide_id or "").strip().lower(),
            hwnd=int(hwnd),
            pid=int(pid) if pid else None,
            workspace_root=root,
            mode=mode if mode == "workspace" else "welcome",
            source=source if source in ("icon", "chat") else "chat",
            last_seen_at=time.time(),
        )
        self._ide_hwnd = self._ide_session.hwnd
        self._ide_pid = self._ide_session.pid

    def _clear_ide_session(self, reason: str = "") -> None:
        was_companion = self._ui_mode == "ide_companion"
        self._ide_session = IdeSession()
        self._ide_hwnd = None
        self._ide_pid = None
        if was_companion:
            self._apply_ide_companion_layout(False)
        if reason:
            self._live_activity.append_instant_line(f"IDE session 해제: {reason}")

    def _get_bound_ide_session(self, *, refresh: bool = True) -> IdeSession | None:
        if refresh:
            self._refresh_ide_session_state()
        return self._ide_session if self._ide_session.active else None

    def _refresh_ide_session_state(self) -> None:
        session = self._ide_session
        if not session.active:
            self._ide_hwnd = None
            self._ide_pid = None
            return
        preferred = self._current_preferred_ide()
        if session.ide_id != preferred:
            self._clear_ide_session("preferred IDE 변경")
            return
        hwnd = session.hwnd
        if not self._ide_hwnd_alive(hwnd):
            self._clear_ide_session("IDE 창 종료")
            return
        if session.mode == "workspace" and session.workspace_root:
            try:
                from iris.automation.ide_input import get_window_title

                title = (get_window_title(int(hwnd)) or "").lower()
                workspace_name = Path(session.workspace_root).name.lower()
                generic_titles = {"cursor", "cursor agents", "visual studio code", "code"}
                # ponytail: Browser Tab 같은 제목은 workspace 이름이 안 보여도 세션 유지.
                # 완전한 웰컴/기본 제목으로 돌아간 경우만 문맥 상실로 본다.
                if workspace_name and title and title.strip() in generic_titles:
                    self._clear_ide_session("workspace 문맥 상실")
                    return
            except Exception:
                pass
        session.last_seen_at = time.time()
        self._ide_session = session
        self._ide_hwnd = session.hwnd
        self._ide_pid = session.pid

    def _find_workspace_window(
        self,
        ide_id: str,
        workspace_root: str,
    ) -> tuple[int | None, int | None, str]:
        root_name = Path(workspace_root).name.strip().lower()
        if not root_name:
            return None, None, ""
        wins = list_ide_windows(ide_id, load_user_profile(self._db).ide_exe_path)
        for win in wins:
            title = str(win.get("title") or "").strip()
            if root_name in title.lower():
                return int(win["hwnd"]), int(win["pid"]), title
        return None, None, ""

    def _schedule_companion_retile(self, ide_hwnd: int) -> None:
        """Cursor가 자체 레이아웃으로 되돌리는 경우 대비 지연 재타일."""
        hwnd = int(ide_hwnd)

        def _retile() -> None:
            if self._ui_mode != "ide_companion":
                return
            if not self._ide_hwnd_alive(hwnd):
                return
            tile_ide_and_iris(hwnd, self, ide_ratio=0.7)

        QTimer.singleShot(400, _retile)
        QTimer.singleShot(1200, _retile)
        QTimer.singleShot(2500, _retile)

    def _activate_companion_tile(self, hwnd: int, *, label: str = "") -> str:
        """IDE 창이 준비된 뒤: Companion 레이아웃 → 70:30 타일.

        순서: (1) IDE 이미 뜸 (2) Iris 세로 레이아웃 (3) 타일.
        """
        from PyQt6.QtWidgets import QApplication

        self._ide_hwnd = int(hwnd)
        # 1) Iris companion UI (min size 축소 포함)
        self._apply_ide_companion_layout(True)
        QApplication.processEvents()
        # 2) 타일
        ok, tile_err = tile_ide_and_iris(self._ide_hwnd, self, ide_ratio=0.7)
        if not ok:
            self._apply_ide_companion_layout(False)
            return tile_err or "tile failed"
        self._fit_companion_orb_to_width()
        self._viz.request_sync_orb_anchor("ide_companion_tiled")
        self._schedule_companion_retile(self._ide_hwnd)
        if label:
            self._live_activity.append_instant_line(f"IDE Companion: {label} tiled 70:30")
        return ""

    def _enter_ide_companion(self, *, source: str = "icon") -> None:
        profile = load_user_profile(self._db)
        ide_id = (profile.preferred_ide or "cursor").strip().lower() or "cursor"
        exe, err = resolve_ide_exe(ide_id, profile.ide_exe_path)
        if err or not exe:
            self._live_activity.append_instant_line(err or "IDE를 찾을 수 없습니다.")
            if ide_id != "custom":
                show_ide_not_installed_dialog(self, ide_id)
            return

        from PyQt6.QtWidgets import QApplication
        import time as _time

        session = self._get_bound_ide_session(refresh=True)
        if session is not None and session.ide_id == ide_id and session.hwnd is not None:
            err2 = self._activate_companion_tile(int(session.hwnd), label=f"{ide_id} (bound)")
            if err2:
                self._live_activity.append_instant_line(f"타일 배치 실패: {err2}")
                return
            self._bind_ide_session(
                ide_id=ide_id,
                hwnd=int(session.hwnd),
                pid=session.pid,
                workspace_root=session.workspace_root,
                mode=session.mode,
                source=source,
            )
            self._live_activity.append_instant_line("기존 bound IDE session 재사용")
            return

        project_root = self._current_project_root()
        if project_root:
            hwnd2, pid2, title2 = self._find_workspace_window(ide_id, project_root)
            if hwnd2 is not None:
                err2 = self._activate_companion_tile(int(hwnd2), label=title2 or Path(project_root).name)
                if err2:
                    self._live_activity.append_instant_line(f"타일 배치 실패: {err2}")
                    return
                self._bind_ide_session(
                    ide_id=ide_id,
                    hwnd=int(hwnd2),
                    pid=pid2,
                    workspace_root=project_root,
                    mode="workspace",
                    source=source,
                )
                self._live_activity.append_instant_line("기존 프로젝트 Cursor 창을 bound session으로 재사용")
                return
            err3 = self._open_ide_folder(project_root, new_window=True, source=source)
            if err3:
                self._live_activity.append_instant_line(f"IDE 프로젝트 열기 실패: {err3}")
            return

        hwnd = None
        pid = None
        if hwnd is None:
            before = {
                int(w["hwnd"])
                for w in list_ide_windows(ide_id, profile.ide_exe_path)
            }
            launched_pid, launch_err = launch_ide(
                ide_id,
                ide_exe_path=profile.ide_exe_path,
                ide_cli_path=profile.ide_cli_path,
                project_root="",
                new_window=True,
            )
            if launch_err:
                self._live_activity.append_instant_line(f"IDE 실행 실패: {launch_err}")
                return
            pid = launched_pid or pid
            self._live_activity.append_instant_line("IDE 창을 기다리는 중…")
            # 순서 1: IDE가 먼저 뜰 때까지 Iris 레이아웃은 유지
            hwnd = None
            title = ""
            deadline = _time.monotonic() + 14.0
            while _time.monotonic() < deadline:
                QApplication.processEvents()
                hwnd, wait_pid, title = wait_for_new_ide_window(
                    ide_id,
                    ide_exe_path=profile.ide_exe_path,
                    exclude_hwnds=before,
                    title_substr="",
                    timeout_sec=0.45,
                )
                if wait_pid:
                    pid = wait_pid
                if hwnd is not None and int(hwnd) not in before:
                    break
                hwnd = None
                _time.sleep(0.2)
            if hwnd is None:
                self._live_activity.append_instant_line(
                    "IDE는 시작됐지만 창을 찾지 못했습니다. 수동으로 창을 연 뒤 다시 시도하세요."
                )
                return

        # 순서 2~3: Companion 레이아웃 + 70:30
        spec = get_ide_spec(ide_id)
        name = spec.name if spec else ide_id
        err2 = self._activate_companion_tile(int(hwnd), label=f"{name} (70:30)")
        if err2:
            self._live_activity.append_instant_line(f"타일 배치 실패: {err2}")
            return
        self._bind_ide_session(
            ide_id=ide_id,
            hwnd=int(hwnd),
            pid=pid,
            workspace_root="",
            mode="welcome",
            source=source,
        )
        self._live_activity.append_instant_line(
            f"IDE Companion: {name}. 바이브코딩은 Iris 채팅으로."
        )

    def _open_ide_folder(self, folder: str, *, new_window: bool = True, source: str = "chat") -> str:
        """폴더를 IDE에서 열고 Companion 타일(IDE 80%). 실패 시 에러 문자열."""
        from pathlib import Path
        from PyQt6.QtWidgets import QApplication
        import time as _time

        root = Path(folder).expanduser()
        if not root.is_dir():
            return f"not a directory: {folder}"
        root_s = str(root.resolve())

        profile = load_user_profile(self._db)
        ide_id = (profile.preferred_ide or "cursor").strip().lower() or "cursor"
        exe, err = resolve_ide_exe(ide_id, profile.ide_exe_path)
        if err or not exe:
            if ide_id != "custom":
                show_ide_not_installed_dialog(self, ide_id)
            return err or "IDE not found"

        profile.project_root = root_s
        save_user_profile(self._db, profile)

        session = self._get_bound_ide_session(refresh=True)
        if session is None:
            existing_hwnd, existing_pid, existing_title = self._find_workspace_window(ide_id, root_s)
            if existing_hwnd is not None:
                err2 = self._activate_companion_tile(
                    int(existing_hwnd),
                    label=existing_title or root.name,
                )
                if err2:
                    return err2
                self._bind_ide_session(
                    ide_id=ide_id,
                    hwnd=int(existing_hwnd),
                    pid=existing_pid,
                    workspace_root=root_s,
                    mode="workspace",
                    source=source,
                )
                return ""
        if session is not None and session.ide_id == ide_id and session.hwnd is not None and not new_window:
            try:
                from iris.automation.ide_input import force_focus_hwnd, get_window_title

                force_focus_hwnd(int(session.hwnd))
            except Exception:
                pass
            launched_pid, launch_err = open_folder_in_ide(
                ide_id,
                root_s,
                ide_exe_path=profile.ide_exe_path,
                ide_cli_path=profile.ide_cli_path,
                new_window=False,
                reuse_window=True,
            )
            if launch_err:
                return launch_err
            deadline = _time.monotonic() + 10.0
            while _time.monotonic() < deadline:
                QApplication.processEvents()
                try:
                    from iris.automation.ide_input import get_window_title

                    title = (get_window_title(int(session.hwnd)) or "").lower()
                    if root.name.lower() in title:
                        err2 = self._activate_companion_tile(int(session.hwnd), label=root.name)
                        if err2:
                            return err2
                        self._bind_ide_session(
                            ide_id=ide_id,
                            hwnd=int(session.hwnd),
                            pid=launched_pid or session.pid,
                            workspace_root=root_s,
                            mode="workspace",
                            source=source,
                        )
                        return ""
                except Exception:
                    pass
                _time.sleep(0.2)
            return "bound IDE session did not confirm requested workspace"

        # 순서 1: IDE 폴더 창을 먼저 연다 (Iris 레이아웃은 아직 유지)
        before = {
            int(w["hwnd"])
            for w in list_ide_windows(ide_id, profile.ide_exe_path)
        }
        if self._ide_hwnd_alive(self._ide_hwnd):
            before.add(int(self._ide_hwnd))

        launched_pid, launch_err = open_folder_in_ide(
            ide_id,
            root_s,
            ide_exe_path=profile.ide_exe_path,
            ide_cli_path=profile.ide_cli_path,
            new_window=new_window,
            reuse_window=False,
        )
        if launch_err:
            self._live_activity.append_instant_line(f"IDE 폴더 열기 실패: {launch_err}")
            return launch_err

        self._live_activity.append_instant_line(f"IDE 폴더 여는 중: {root_s}")

        hwnd = None
        pid = launched_pid or self._ide_pid
        title = ""
        deadline = _time.monotonic() + 14.0
        while _time.monotonic() < deadline:
            QApplication.processEvents()
            hwnd, wait_pid, title = wait_for_new_ide_window(
                ide_id,
                ide_exe_path=profile.ide_exe_path,
                exclude_hwnds=before,
                title_substr=root.name,
                timeout_sec=0.5,
            )
            if wait_pid:
                pid = wait_pid
            if hwnd is not None and int(hwnd) not in before:
                break
            hwnd = None
            _time.sleep(0.2)
        if hwnd is None:
            hwnd2, pid2, title2 = self._find_workspace_window(ide_id, root_s)
            if hwnd2 is not None:
                hwnd = hwnd2
                pid = pid2 or pid
                title = title2 or title
        if hwnd is None:
            return "IDE folder launch started but window not found"

        # 순서 2~3: Companion + 타일
        label = title or root.name
        err2 = self._activate_companion_tile(int(hwnd), label=label)
        if err2:
            return err2
        self._bind_ide_session(
            ide_id=ide_id,
            hwnd=int(hwnd),
            pid=pid,
            workspace_root=root_s,
            mode="workspace",
            source=source,
        )
        return ""

    def _exit_ide_companion(self) -> None:
        """Companion 해제 + bound session 해제."""
        self._clear_ide_session("companion 종료")
        self._live_activity.append_instant_line("IDE Companion 종료")

    def _companion_iris_rect(self):
        return compute_tile_rects(work_area_for(self)).iris

    def _fit_companion_orb_to_width(self) -> None:
        """이메일 우측 Iris 패널과 동일 구체 슬롯·스케일."""
        self._orb_spacer.setMinimumHeight(EMAIL_ORB_HEIGHT)
        self._orb_spacer.setMaximumHeight(EMAIL_ORB_HEIGHT)
        self._viz.particle_core().set_size_scale(EMAIL_ORB_SCALE)

    def _mount_companion_body(self, iris_w: int, iris_h: int) -> None:
        act_h = max(72, min(110, int(iris_h * 0.11)))
        # addWidget만으로 이동 — removeWidget/setParent(None) 없음
        self._companion_page.mount(
            orb_spacer=self._orb_spacer,
            live_activity=self._live_activity,
            chat=self._chat,
            orb_height=EMAIL_ORB_HEIGHT,
            activity_height=act_h,
        )
        self._body_stack.setCurrentWidget(self._companion_page)
        self._viz.particle_core().set_size_scale(EMAIL_ORB_SCALE)
        self._viz.set_orb_anchor(self._orb_spacer)
        self._viz.set_companion_orb_placement(True)
        self._cyberspace_bg.set_orb_above_ui(False)

    def _unmount_companion_body(self) -> None:
        self._cyberspace_bg.set_orb_above_ui(False)
        self._viz.set_companion_orb_placement(False)
        self._orb_spacer.setMinimumHeight(self._orb_spacer_min_h)
        self._orb_spacer.setMaximumHeight(16777215)
        self._orb_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._live_activity.setMinimumHeight(72)
        self._live_activity.setMaximumHeight(180)
        self._live_activity.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._chat.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        left_lay = self._assistant_page.center_layout
        if self._companion_page.is_mounted():
            self._companion_page.transfer_to(left_lay, (2, 0, 3))
        else:
            left_lay.addWidget(self._orb_spacer, 2)
            left_lay.addWidget(self._live_activity, 0)
            left_lay.addWidget(self._chat, 3)
            self._orb_spacer.show()
            self._live_activity.show()
            self._chat.show()
        self._body_stack.setCurrentWidget(self._main_splitter)
        self._viz.set_orb_anchor(self._orb_spacer)
        self._viz.particle_core().set_size_scale(1.0)

    def _apply_ide_companion_layout(self, companion: bool) -> None:
        if companion:
            if self._ui_mode == "ide_companion":
                self._drag.set_ide_companion_active(True)
                self._set_workspace_icon_active("ide")
                return
            self._companion_saved_geometry = QRect(self.normalGeometry())
            if self._companion_saved_geometry.isNull() or not self._companion_saved_geometry.isValid():
                self._companion_saved_geometry = QRect(self.geometry())
            self._companion_saved_sizes = self._main_splitter.sizes()
            self._companion_saved_assistant_sizes = self._assistant_page.splitter.sizes()
            self._companion_saved_min_size = self.minimumSize()
            self._show_assistant_workspace()

            iris = self._companion_iris_rect()
            self.setMinimumSize(min(260, iris.width()), min(480, iris.height()))
            self._root_lay.setContentsMargins(6, 4, 6, 4)
            self._mount_companion_body(iris.width(), iris.height())

            self._ui_mode = "ide_companion"
            self._drag.set_ide_companion_active(True)
            self._set_workspace_icon_active("ide")
            self._viz.request_sync_orb_anchor("ide_companion_enter")
            return

        if self._ui_mode != "ide_companion":
            return
        self._unmount_companion_body()
        self._root_lay.setContentsMargins(*self._normal_root_margins)
        if self._companion_saved_min_size is not None:
            self.setMinimumSize(self._companion_saved_min_size)
        else:
            self.setMinimumSize(960, 640)
        # 상태행은 set_ide_companion_active(False)가 status_column만 다시 보여줌.
        # backend_row()는 레거시 빈 위젯 — show()하면 parent 없는 top-level 흰 창이 됨.
        if self._companion_saved_sizes:
            self._main_splitter.setSizes(self._companion_saved_sizes)
        if self._companion_saved_assistant_sizes:
            self._assistant_page.splitter.setSizes(self._companion_saved_assistant_sizes)
        saved = self._companion_saved_geometry
        if saved is not None and saved.isValid():
            if self.isMaximized():
                self.showNormal()
            self.setGeometry(saved)
        self._ui_mode = "normal"
        self._drag.set_ide_companion_active(False)
        self._set_workspace_icon_active(None)
        self._viz.request_sync_orb_anchor("ide_companion_exit")

    def _on_mobile_icon(self) -> None:
        if is_emulator_running():
            if is_emulator_headless():
                self._live_activity.append_instant_line(
                    "Headless Android 에뮬레이터 감지 — 창 있는 인스턴스로 재시작합니다."
                )
                try:
                    proc = restart_emulator_windowed()
                    self._live_activity.append_instant_line(
                        f"Android 에뮬레이터 재시작 (PID {proc.pid}) — android-emulator/data"
                    )
                except OSError as exc:
                    self._live_activity.append_instant_line(f"에뮬레이터 재시작 실패: {exc}")
                    self._notes.try_add_alert(
                        target_id=0,
                        category="ERROR",
                        title="Android 에뮬레이터",
                        message=str(exc),
                    )
                return
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
        dlg.exec()

    def _open_settings_dialog(self) -> None:
        if self._mic_listen_active:
            self._stop_mic_listen()
        dlg = SettingsDialog(self._settings, self._db, self)
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
            self._voice_prefs = sel.voice_prefs
            self._settings.always_listen_speech_rms = self._voice_prefs.stt_speech_rms
            self._chat.set_speech_threshold_rms(self._voice_prefs.stt_speech_rms)
            self._recorder.set_speech_rms(self._voice_prefs.stt_speech_rms)
            self._voice_runtime.set_base_url(self._voice_prefs.voice_runtime_url)
            self._status_header.set_tts_status(
                "READY" if self._voice_prefs.tts_enabled else "OFF"
            )
            self._saved_model = sel.ollama_model.strip()
            if self._saved_model:
                save_selected_model(self._db, self._saved_model)
            self._status_header.set_model_name(self._settings.model_name or "(unset)")
            self._refresh_hermes_health()
            if self._settings.hermes_enabled and self._saved_model:
                self._sync_hermes_model(self._saved_model)
            self._refresh_models()
            self._refresh_ide_session_state()
            if self._workspace_mode == "email":
                accounts = load_email_accounts(self._db)
                self._left_sidebar.email_folder.set_accounts(
                    accounts, selected_id=self._selected_email_account_id
                )
                if accounts:
                    self._refresh_email_inbox()
                else:
                    self._left_sidebar.email_folder.set_status(
                        "설정에서 이메일 계정을 추가하세요."
                    )

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
            stop_control_surface(self)
            if self._recorder.is_recording():
                self._recorder.cancel_recording()
            self._stop_tts_playback()
            if self._chat_worker is not None and self._chat_worker.isRunning():
                cancel = getattr(self._chat_worker, "request_cancel", None)
                if callable(cancel):
                    cancel()
                self._chat_worker.wait(1500)
            if self._stt_worker is not None and self._stt_worker.isRunning():
                self._stt_worker.wait(1500)
            if self._tts_worker is not None and self._tts_worker.isRunning():
                self._tts_worker.wait(1500)
            self._tts_player.stop()
            if self._email_chat_worker is not None and self._email_chat_worker.isRunning():
                self._email_chat_worker.request_cancel()
                self._email_chat_worker.wait(1500)
            if self._boot_checks_worker is not None and self._boot_checks_worker.isRunning():
                self._boot_checks_worker.wait(3000)
            self._metrics_worker.request_stop()
            self._metrics_worker.wait(2000)
            self._api_quota_worker.request_stop()
            self._api_quota_worker.wait(2000)
            self._voice_runtime.shutdown(timeout_sec=2.0)
        except Exception:
            pass
        super().closeEvent(event)
