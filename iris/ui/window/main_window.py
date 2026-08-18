"""메인 PyQt6 창 — Ollama 모델 선택 + Hermes/Ollama 채팅."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path
import time

from PyQt6.QtCore import QEvent, QRect, Qt, QThread, QTimer
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from iris.assets.branding import APP_DISPLAY_NAME, load_app_icon
from iris.audio.pcm_player import PcmPlayer
from iris.audio.recorder import AudioRecorder, RecordingResult
from iris.audio.text_normalizer import load_pronunciation_map, split_tts_sentences
from iris.audio.tts_pipeline import TtsSentencePump, should_start_tts_synth
from iris.audio.voice_runtime_manager import VoiceRuntimeProcessManager
from iris.audio.workers import (
    STTTranscriptionWorker,
    TTSRuntimeBootstrapWorker,
    TTSStreamWorker,
    TTSWarmupWorker,
)
from iris.config.settings import load_settings
from iris.core.activity_sink import register_activity_sink
from iris.core.state_machine import AppState, StateMachine
from iris.infrastructure.api_model_meta import (
    api_model_supports_tools,
    filter_nvidia_free_endpoint_models,
    is_nvidia_provider,
)
from iris.infrastructure.ollama_client import OllamaModelInfo
from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.api_providers import (
    get_api_provider,
    is_api_runtime_model,
    load_api_providers,
    parse_runtime_model_id,
    runtime_model_id,
)
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
    is_cursor_agents_title,
    is_generic_ide_title,
    launch_ide,
    list_ide_windows,
    open_folder_in_ide,
    resolve_ide_exe,
    wait_for_new_ide_window,
    workspace_title_lost_context,
)
from iris.system.ide_tiler import (
    compute_tile_rects,
    place_hwnd,
    place_qt_window,
    read_ide_rect,
    tile_ide_and_iris,
    work_area_for,
)
from iris.system.metrics_worker import MetricsWorker
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.widgets.context_ring import estimate_messages_tokens
from iris.ui.window.cyberspace_background import CyberspaceBackground
from iris.ui.shared.cyberspace_theme import apply_cyberspace_theme
from iris.ui.widgets.drag_tab import DragTab
from iris.ui.window.frameless_chrome import FramelessShell, center_on_screen, suppress_native_window_border
from iris.ui.sidebar.left_sidebar_panel import LeftSidebarPanel
from iris.ui.monitor.live_activity_panel import LiveActivityPanel, UiActivityRelay
from iris.ui.notification.notification_panel import NotificationPanel
from iris.ui.workers.boot_checks_worker import BootChecksWorker
from iris.ui.control_bindings import (
    mark_control_ready,
    start_control_surface,
    stop_control_surface,
)
from iris.ui.workers.email_workers import EmailInboxWorker, EmailMessageWorker, EmailSendWorker
from iris.ui.workers.hermes_workers import (
    HermesChatWorker,
    HermesHealthWorker,
    HermesModelSyncWorker,
)
from iris.ui.workers.ollama_workers import OllamaChatWorker, OllamaModelListWorker
from iris.ui.workers.api_provider_workers import OpenAICompatChatWorker
from iris.ui.workers.learning_workers import LearningProcessWorker
from iris.learning.manager import LearningManager
from iris.learning.models import LearningState
from iris.learning.aloha_learner import AlohaLearner, MockLearner
from iris.learning.aloha_executor import MockExecutor
from iris.learning.vlm_policy import (
    evaluate_api_fallback,
    evaluate_ollama_model,
    list_learning_vlm_models,
)
from iris.learning.aloha_learner import _load_vlm_keys
from iris.learning.hook_probe import probe_input_hooks
from iris.learning.permission import policy_for, request_elevation_hint
from iris.storage.learning_prefs import (
    LearningPreferences,
    load_learning_preferences,
    save_learning_preferences,
)
from iris.ui.learning.vlm_guide_dialog import VlmGuideDialog
from iris.infrastructure.ollama_client import OllamaClient
from iris.ui.settings.settings_dialog import SettingsDialog
from iris.ui.window.startup_intro import StartupIntroAnimator
from iris.ui.shared.theme_tokens import TOKENS
from iris.ui.window.top_status_header import TopStatusHeader
from iris.ui.monitor.unified_monitor_panel import UnifiedMonitorPanel
from iris.monitoring.pin_store import PinStore
from iris.monitoring.pinned_monitor import PinnedMonitorService
from iris.ui.settings.user_profile_dialog import UserProfileDialog
from iris.ui.widgets.ide_icons import show_ide_not_installed_dialog
from iris.ui.widgets.visualizer import Visualizer
from iris.ui.workspaces.assistant_workspace_page import AssistantWorkspacePage
from iris.ui.workspaces.calendar_workspace_page import CalendarWorkspacePage
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
    """IRIS — Hermes API 또는 Ollama 채팅 HUD."""

    def __init__(self, *, test_mode: bool = False) -> None:
        super().__init__()
        self._test_mode = test_mode
        self.setWindowTitle(APP_DISPLAY_NAME)
        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setMinimumSize(960, 640)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._env_path = Path(__file__).resolve().parents[3] / ".env"
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
        self._pending_local_vibe_prompt = ""
        self._chat_worker: QThread | None = None
        self._stt_worker: STTTranscriptionWorker | None = None
        self._tts_worker: TTSStreamWorker | None = None
        self._tts_cancelled_workers: list[TTSStreamWorker] = []
        self._tts_warmup_worker: TTSWarmupWorker | None = None
        self._tts_warmup_model = ""
        self._tts_runtime_ready = False
        self._tts_bootstrap_worker: TTSRuntimeBootstrapWorker | None = None
        self._model_worker: OllamaModelListWorker | None = None
        self._hermes_health_worker: HermesHealthWorker | None = None
        self._hermes_model_worker: HermesModelSyncWorker | None = None
        self._email_inbox_worker: EmailInboxWorker | None = None
        self._email_message_worker: EmailMessageWorker | None = None
        self._email_send_worker: EmailSendWorker | None = None
        self._email_chat_worker: HermesChatWorker | None = None
        self._email_history: list[dict[str, str]] = []
        self._email_busy = False
        self._calendar_chat_worker: HermesChatWorker | None = None
        self._calendar_history: list[dict[str, str]] = []
        self._calendar_busy = False
        self._boot_checks_worker: BootChecksWorker | None = None
        self._boot_checks_done = False
        self._learning_worker: LearningProcessWorker | None = None
        self._email_preloaded = False
        self._tts_queue: list[str] = []
        self._tts_job_id = 0
        self._tts_stopping = False
        self._tts_active_play = False
        self._tts_active_msg_id: str = ""
        self._tts_pump: TtsSentencePump | None = None
        self._tts_input_finished = True
        self._tts_stream_had_content = False
        self._tts_pcm_job_id: int | None = None
        self._tts_pcm_ending = False
        self._tts_perf: dict[str, float] = {}
        self._tts_perf_logged = False
        self._tts_pump_timer = QTimer(self)
        self._tts_pump_timer.setInterval(80)
        self._tts_pump_timer.timeout.connect(self._poll_tts_pump)
        self._email_view: tuple[str, str] = ("inbox", "")  # (folder_key, gmail_category)
        self._email_folder = "inbox"  # 메시지 조회용 메일함 키
        self._selected_email_account_id = ""
        self._hermes_online = False
        self._busy = False
        self._ignore_chat_result = False
        self._api_fallback_pending = False  # 직접 호출 실패 → Hermes 폴백 1회
        self._api_fallback_model = ""  # Hermes에 넘길 모델 id
        self._quota_by_key: dict[str, object] = {}
        self._last_ollama_quota_refresh = 0.0
        self._workspace_mode = "assistant"
        self._ui_mode = "normal"  # "normal" | "ide_companion"
        self._ide_hwnd: int | None = None
        self._ide_pid: int | None = None
        self._ide_session = IdeSession()
        self._ide_session_watch = QTimer(self)
        self._ide_session_watch.setInterval(2000)
        self._ide_session_watch.timeout.connect(self._refresh_ide_session_state)
        self._ide_session_watch.start()
        # companion 모드에서 사용자가 IDE나 Iris 창 경계를 직접 드래그하면 반대쪽도
        # 따라 움직이게 — 두 창 다 폴링해서 마지막으로 우리가 배치한 값과 다르면 재배치.
        self._last_synced_ide_rect: QRect | None = None
        self._last_synced_iris_rect: QRect | None = None
        self._companion_sync_timer = QTimer(self)
        self._companion_sync_timer.setInterval(600)
        self._companion_sync_timer.timeout.connect(self._sync_companion_split)
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
            iris_root=Path(__file__).resolve().parents[3],
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
        self._pcm_player = PcmPlayer(self)
        self._pcm_player.set_volume(self._voice_prefs.tts_volume)
        self._pcm_player.set_voice_effect(
            enabled=self._voice_prefs.tts_ai_voice_fx_enabled,
            intensity=self._voice_prefs.tts_ai_voice_fx_intensity,
        )
        self._pcm_player.speakers_opened.connect(self._on_pcm_speakers_opened)
        self._pcm_player.drained.connect(self._on_pcm_drained)
        self._pcm_player.failed.connect(self._on_pcm_failed)
        self._media_audio_out = QAudioOutput(self)
        self._media_audio_out.setVolume(self._voice_prefs.tts_volume)
        self._media_player = QMediaPlayer(self)
        self._media_player.setAudioOutput(self._media_audio_out)
        self._media_player.playbackStateChanged.connect(self._on_media_playback_state)

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
        self._drag.learning_clicked.connect(self._on_learning_toggle)
        self._drag.mic_clicked.connect(self._on_chat_mic_clicked)
        root.addWidget(self._drag)

        # 업무 학습 — test_mode에서는 mock learner/executor
        self._learning_prefs = load_learning_preferences(self._db)
        if self._test_mode:
            from iris.learning.workflow_registry import LearnedWorkflowRepository

            repo = LearnedWorkflowRepository(self._db)
            self._learning = LearningManager(
                self._db,
                learner=MockLearner(),
                executor=MockExecutor(repo),
                on_state=self._on_learning_state,
                on_activity=lambda line: self._live_activity.append_instant_line(line)
                if hasattr(self, "_live_activity")
                else None,
                iris_hwnd_provider=self._iris_learning_hwnds,
                learning_prefs=self._learning_prefs,
            )
        else:
            self._learning = LearningManager(
                self._db,
                learner=self._build_aloha_learner(),
                on_state=self._on_learning_state,
                on_activity=lambda line: self._live_activity.append_instant_line(line)
                if hasattr(self, "_live_activity")
                else None,
                iris_hwnd_provider=self._iris_learning_hwnds,
                learning_prefs=self._learning_prefs,
            )

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
        self._calendar_page = CalendarWorkspacePage()
        self._workspace_stack.addWidget(self._assistant_page)
        self._workspace_stack.addWidget(self._obsidian_page)
        self._workspace_stack.addWidget(self._email_page)
        self._workspace_stack.addWidget(self._calendar_page)
        splitter.addWidget(self._workspace_stack)

        self._companion_page = IdeCompanionPage()
        self._body_stack = QStackedWidget()
        self._body_stack.setObjectName("MainBodyStack")
        self._body_stack.addWidget(splitter)
        self._body_stack.addWidget(self._companion_page)

        self._iris_wiki = IrisWiki(Path(__file__).resolve().parents[3] / "obsidian-vault")
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
        self._calendar_page.calendar_chat_send.connect(self._on_calendar_chat_send)
        self._calendar_page.add_event_requested.connect(self._on_calendar_add_event)
        self._calendar_page.delete_event_requested.connect(self._on_calendar_delete_event)
        self._calendar_page.month_changed.connect(self._on_calendar_month_changed)
        self._calendar_page.refresh_holidays_requested.connect(self._refresh_calendar_holidays)
        self._calendar_remind_timer = QTimer(self)
        self._calendar_remind_timer.setInterval(60_000)
        self._calendar_remind_timer.timeout.connect(self._check_calendar_reminders)
        if not self._test_mode:
            self._calendar_remind_timer.start()

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
        self._chat.stop_clicked.connect(self._on_chat_stop)
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

        # 고정(📌) 창 AI 감시 — 최대 3개, 30초 주기로 화면을 분석해 상태 변화를 알림
        self._pin_store = PinStore(self._db)
        self._pinned_monitor = PinnedMonitorService(
            self._pin_store,
            self._settings,
            lambda: self._chat.current_model() or self._settings.ollama_model,
            self,
        )
        self._monitor.set_pin_store(self._pin_store)
        self._monitor.pin_changed.connect(self._on_pin_changed)
        self._pinned_monitor.updated.connect(self._monitor.rerender_pins)
        self._pinned_monitor.report.connect(self._on_pinned_report)
        self._pinned_monitor.start()

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
            ("calendar", "calendar", "캘린더"),
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
            elif action_id == "calendar":
                callback = self._on_calendar_icon
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
        self._left_sidebar.utility.metrics.ollama_refresh_requested.connect(
            self._on_ollama_quota_manual_refresh
        )
        if not self._test_mode:
            self._metrics_worker.start()
            self._api_quota_worker.start()
            # 시작 시 선택 모델이 클라우드면 짧은 폴링
            boot_model = (
                self._chat.current_model()
                or self._saved_model
                or self._settings.ollama_model
                or ""
            )
            self._api_quota_worker.set_cloud_polling(self._is_cloud_model(boot_model))
            self._maybe_refresh_ollama_quota(force=True)

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
            from iris.system.setup_protocol import is_setup_preview, mark_core_ready_if_healthy

            if is_setup_preview():
                # 미리보기/데모: 실제 설치 상태와 무관하게 위저드 강제
                QTimer.singleShot(40, self._show_first_run_setup)
            elif mark_core_ready_if_healthy(
                ollama_base_url=self._settings.ollama_base_url,
                hermes_base_url=self._settings.hermes_base_url,
                hermes_command=self._settings.hermes_command,
            ):
                self._start_runtime_boot()
            else:
                # 첫 실행 — 위저드 완료 전엔 Hermes/채팅 부팅 보류
                QTimer.singleShot(40, self._show_first_run_setup)
        else:
            self._chat.append_message("Iris", self._ready_status_message())

    def _show_first_run_setup(self) -> None:
        from iris.config.settings import load_settings
        from iris.system.setup_protocol import is_core_ready, is_setup_preview
        from iris.ui.window.setup_wizard import SetupWizard

        dlg = SetupWizard(self._settings, mode="first_run", parent=self)
        self._setup_wizard = dlg
        try:
            dlg.exec()
        finally:
            self._setup_wizard = None
        if is_core_ready() or is_setup_preview():
            self._settings = load_settings(self._env_path)
            self._start_runtime_boot()
        else:
            self._notes.try_add_alert(
                target_id=0,
                category="ERROR_DETECTED",
                title="시작 프로토콜",
                message="Core가 준비되지 않았습니다. 설정에서 「환경 다시 설정」을 실행하세요.",
                focus_hint="",
                event_id=0,
            )

    def _start_runtime_boot(self) -> None:
        """Core Ready 이후(또는 이미 완료된 환경) 기존 부팅 흐름."""
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
        QTimer.singleShot(900, self._schedule_tts_runtime_bootstrap)

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
            title=APP_DISPLAY_NAME,
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

    def _append_ok_api_models(self, items: list[OllamaModelInfo]) -> list[OllamaModelInfo]:
        """status==ok 커스텀 API 모델을 피커 목록에 병합."""
        out = list(items)
        seen = {m.name for m in out}
        try:
            providers = load_api_providers(self._db)
        except Exception:
            return out
        for p in providers:
            # 정상(ok)이거나, 모델 목록이 있으면 피커에 노출 (채팅에서 직접 호출 시도)
            if not p.enabled or not p.base_url:
                continue
            if p.status != "ok" and not p.models:
                continue
            model_ids = list(p.models)
            if is_nvidia_provider(p.name, p.base_url):
                # 카탈로그 전체가 아니라 무료 Public API 엔드포인트만
                model_ids = filter_nvidia_free_endpoint_models(model_ids)
            for model in model_ids:
                rid = runtime_model_id(p.id, model)
                if rid in seen:
                    continue
                seen.add(rid)
                out.append(
                    OllamaModelInfo(
                        name=rid,
                        catalog_name=f"{p.name} · {model}",
                        supports_tools=api_model_supports_tools(
                            p.name, model, base_url=p.base_url
                        ),
                        requires_subscription=False,
                    )
                )
        return out

    def _on_models_loaded(self, models: object) -> None:
        items: list[OllamaModelInfo] = list(models) if isinstance(models, list) else []
        items = self._append_ok_api_models(items)
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
            n_api = sum(1 for m in items if is_api_runtime_model(m.name))
            n_cloud = sum(
                1
                for m in items
                if getattr(m, "is_cloud", False) and not is_api_runtime_model(m.name)
            )
            n_local = len(items) - n_cloud - n_api
            self._live_activity.append_instant_line(
                f"Models: {n_local} local + {n_cloud} cloud + {n_api} API"
            )
            if self._settings.hermes_enabled and chosen and not is_api_runtime_model(chosen):
                self._sync_hermes_model(chosen)
        else:
            self._chat.set_model_status("(모델 없음)")
        if self._intro is not None:
            self._intro.notify_models_ready()
        self._start_boot_checks()

    def _on_models_failed(self, err: str) -> None:
        # Ollama 실패해도 정상 API 모델은 피커에 표시
        api_only = self._append_ok_api_models([])
        if api_only:
            preferred = self._saved_model or ""
            self._chat.set_models(api_only, selected=preferred)
            self._live_activity.append_instant_line(
                f"Ollama 목록 실패 — API 모델 {len(api_only)}개만 표시: {err[:120]}"
            )
            if self._intro is not None:
                self._intro.notify_models_ready()
            self._start_boot_checks()
            return
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
        self._sync_learning_wiki()

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
        if self._settings.hermes_enabled and not is_api_runtime_model(model):
            self._sync_hermes_model(model)
        self._refresh_context_gauge()
        self._api_quota_worker.set_cloud_polling(self._is_cloud_model(model))

    @staticmethod
    def _is_cloud_model(model: str) -> bool:
        if is_api_runtime_model(model):
            return False
        n = (model or "").strip().lower()
        return n.endswith("-cloud") or ":cloud" in n or n.endswith(":cloud")

    def _maybe_refresh_ollama_quota(self, *, force: bool = False) -> None:
        """클라우드 턴 종료 시 Ollama SESS/WEEK만 즉시 1회 (debounce 8s)."""
        model = (
            self._chat.current_model()
            or self._saved_model
            or self._settings.ollama_model
            or ""
        )
        if not force and not self._is_cloud_model(model):
            return
        now = time.monotonic()
        if not force and (now - self._last_ollama_quota_refresh) < 8.0:
            return
        self._last_ollama_quota_refresh = now
        self._api_quota_worker.request_refresh_ollama_now()

    def _on_ollama_quota_manual_refresh(self) -> None:
        """SESS/WEEK 행 클릭 — debounce 무시하고 즉시 갱신."""
        self._live_activity.append_instant_line("Ollama usage refresh…")
        self._maybe_refresh_ollama_quota(force=True)

    def _refresh_context_gauge(self) -> None:
        """선택 모델 컨텍스트 한도 + 실제 전송 메시지 추정 토큰으로 원형 게이지 갱신.

        매 턴 user/assistant append 직후 호출되어 한도 대비 사용량이 누적 상승한다.
        """
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
        # history만이 아니라 시스템/프로젝트 컨텍스트 포함 — 호출마다 실제 페이로드 반영
        try:
            payload = self._chat_messages_with_project_context()
        except Exception:
            payload = list(self._history)
        used = estimate_messages_tokens(payload)
        self._chat.set_context_usage(used, limit)

    # ------------------------------------------------------------------
    # 고정 창 AI 감시
    # ------------------------------------------------------------------

    def _on_pin_changed(self) -> None:
        """고정/해제 직후 — 결과를 오래 기다리지 않도록 즉시 1회 분석."""
        count = self._pin_store.count()
        self._live_activity.append_instant_line(f"AI 감시 대상 {count}개")
        if count:
            self._pinned_monitor.analyze_soon()

    def _on_pinned_report(self, title: str, category: str, headline: str, detail: str) -> None:
        """감시 중인 창의 상태가 주의 필요로 바뀐 순간 — 알림 패널에 띄운다."""
        suppressed = None
        try:
            # target_id 0 = 고정 감시(테이블 등록 대상 아님) — 카테고리 쿨다운만 적용
            suppressed = self._notif_policy.should_suppress(0, category)
        except Exception:
            suppressed = None
        if suppressed:
            return
        self._notes.try_add_alert(
            target_id=0,
            category=category,
            title=f"{headline} — {title[:40]}",
            message=detail or headline,
            focus_hint=title,
            event_id=0,
        )
        try:
            self._notif_policy.mark_shown(0, category)
            self._notif_policy.log_notification(0, 0, category, title, detail or headline)
        except Exception:
            pass

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
        self._ignore_chat_result = False
        self._stop_tts_playback()
        self._begin_auto_tts_response()
        self._api_fallback_pending = False
        self._api_fallback_model = ""
        self._chat.set_generating(True)
        self._state.set_state(AppState.PROCESSING)

        try:
            from iris.system.project_ops import is_code_reveal_request

            self._pending_local_vibe_prompt = text if is_code_reveal_request(text) else ""
        except Exception:
            self._pending_local_vibe_prompt = ""

        if self._use_hermes_backend():
            messages = self._chat_messages_with_project_context()
        messages = self._chat_messages_with_project_context()

        # 커스텀 API 모델 — 직접 호출 우선 (Hermes 에이전트와 병행 가능)
        parsed = parse_runtime_model_id(model)
        if parsed is not None:
            pid, api_model = parsed
            provider = get_api_provider(self._db, pid)
            if provider is None or not provider.base_url:
                self._busy = False
                self._chat.set_generating(False)
                if self._history and self._history[-1].get("role") == "user":
                    self._history.pop()
                self._chat.append_message_instant(
                    "Iris",
                    "선택한 API가 설정에서 삭제되었거나 Base URL이 없습니다. 설정을 확인하세요.",
                )
                self._state.set_state(AppState.IDLE)
                return
            self._api_fallback_pending = True
            self._api_fallback_model = api_model
            worker = OpenAICompatChatWorker(
                provider.base_url,
                provider.api_key,
                api_model,
                messages,
                display_model=f"{provider.name}/{api_model}",
                parent=self,
            )
            self._chat_worker = worker
            worker.connecting.connect(self._on_chat_connecting)
            worker.content_chunk.connect(self._on_content_chunk)
            worker.finished_ok.connect(self._on_chat_finished)
            worker.failed.connect(self._on_chat_failed)
            worker.start()
            return

        if self._use_hermes_backend():
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
            messages,
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

    def _on_chat_stop(self) -> None:
        """생성 중 정지 버튼 — Cursor/GPT처럼 즉시 UI를 멈추고 워커에 취소 요청."""
        if not self._busy:
            return
        self._ignore_chat_result = True
        worker = self._chat_worker
        if worker is not None:
            cancel = getattr(worker, "request_cancel", None)
            if callable(cancel):
                cancel()
        partial = (self._chat.typing_buffer_text or "").strip()
        if getattr(self._chat, "_stream_active", False):
            self._chat.end_stream_message(partial or None)
            if partial:
                self._history.append({"role": "assistant", "content": partial})
                self._last_assistant_text = partial
                self._refresh_context_gauge()
        else:
            self._chat.finish_typing()
        self._busy = False
        self._chat.set_generating(False)
        self._state.set_state(AppState.IDLE)
        self._stop_tts_playback()
        self._tts_pump = None
        self._live_activity.append_instant_line("Stopped.")
        self._maybe_refresh_ollama_quota()

    def _on_hermes_tool_progress(self, message: str) -> None:
        if self._ignore_chat_result:
            return
        text = (message or "").strip()
        if text:
            self._live_activity.append_instant_line(f"[tool] {text}")

    def _on_chat_connecting(self, model: str, host: str) -> None:
        if self._ignore_chat_result:
            return
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
        if self._ignore_chat_result:
            return
        self._live_activity.append_instant_line("Thinking...")

    def _on_thinking_chunk(self, chunk: str) -> None:
        if self._ignore_chat_result:
            return
        self._live_activity.append_instant_chunk(chunk)

    def _on_thinking_done(self) -> None:
        if self._ignore_chat_result:
            return
        self._live_activity.append_instant_line("")
        self._live_activity.append_instant_line("...done thinking.")
        self._live_activity.append_instant_line("")
        self._state.set_state(AppState.RESPONDING)
        self._chat.begin_stream_message(
            "Iris",
            speech_sync=False,
            wait_for_tts_completion=False,
        )

    def _on_content_chunk(self, chunk: str) -> None:
        if self._ignore_chat_result:
            return
        if not getattr(self._chat, "_stream_active", False):
            # thinking 없이 content만 오는 모델
            self._state.set_state(AppState.RESPONDING)
            self._chat.begin_stream_message(
                "Iris",
                speech_sync=False,
                wait_for_tts_completion=False,
            )
        if (chunk or "").strip():
            self._mark_tts_perf("llm_first_content")
        self._chat.append_stream_chunk(chunk)
        self._feed_tts_stream(chunk)

    def _feed_tts_stream(self, chunk: str, *, flush: bool = False) -> None:
        pump = self._tts_pump
        if pump is None:
            return
        if flush:
            self._finish_tts_input()
            return
        if not chunk:
            return
        self._tts_stream_had_content = self._tts_stream_had_content or bool(chunk.strip())
        self._append_tts_chunks(pump.feed(chunk))

    def _begin_auto_tts_response(self) -> None:
        self._tts_pump_timer.stop()
        self._tts_pump = None
        self._tts_input_finished = True
        self._tts_stream_had_content = False
        self._tts_pcm_ending = False
        self._tts_pcm_job_id = None
        self._tts_perf = {"response_start": time.perf_counter()}
        self._tts_perf_logged = False
        if not self._voice_prefs.tts_enabled or self._voice_prefs.tts_mode != "auto":
            return
        mapping = load_pronunciation_map(self._voice_prefs.pronunciation_dict_json)
        self._tts_pump = TtsSentencePump(mapping)
        self._tts_input_finished = False
        self._tts_pump_timer.start()
        self._schedule_tts_runtime_bootstrap()

    def _poll_tts_pump(self) -> None:
        pump = self._tts_pump
        if pump is None or self._tts_input_finished:
            self._tts_pump_timer.stop()
            return
        self._append_tts_chunks(pump.poll())

    def _finish_tts_input(self) -> None:
        if self._tts_input_finished:
            return
        pump, self._tts_pump = self._tts_pump, None
        self._tts_input_finished = True
        self._tts_pump_timer.stop()
        if pump is not None:
            self._append_tts_chunks(pump.flush())
        self._maybe_end_pcm_session()

    def _on_chat_finished(self, content: str) -> None:
        if self._ignore_chat_result:
            self._ignore_chat_result = False
            self._chat_worker = None
            self._busy = False
            self._chat.set_generating(False)
            self._tts_pump = None
            self._maybe_refresh_ollama_quota()
            return
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
            self._try_reveal_local_vibe_code(text)
        self._refresh_context_gauge()
        self._api_fallback_pending = False
        if self._use_hermes_backend() and not self._hermes_online:
            self._hermes_online = True
            self._status_header.refresh_backend_status(
                self._settings,
                hermes_online=True,
            )
        self._busy = False
        self._chat.set_generating(False)
        self._chat_worker = None
        self._mark_tts_perf("llm_finished")
        self._set_tts_orb_warmup(False)
        self._state.set_state(AppState.IDLE)
        self._maybe_refresh_ollama_quota()
        if self._tts_pump is not None and text and not self._tts_stream_had_content:
            self._feed_tts_stream(text)
        self._feed_tts_stream("", flush=True)
        if (
            not self._tts_active_msg_id
            and (
                self._tts_pcm_job_id == self._tts_job_id
                or self._tts_busy()
                or self._tts_queue
            )
        ):
            self._tts_active_msg_id = self._chat._last_tts_id or ""
            if self._tts_active_msg_id:
                if self._tts_active_play:
                    status = "playing"
                elif self._tts_busy() or self._tts_queue:
                    status = "busy"
                else:
                    status = "idle"
                self._chat.set_speaker_status(self._tts_active_msg_id, status)

    def _try_reveal_local_vibe_code(self, assistant_text: str) -> None:
        prompt = self._pending_local_vibe_prompt
        self._pending_local_vibe_prompt = ""
        if not prompt:
            return
        surface = getattr(self, "_control_surface", None)
        if surface is None:
            self._chat.append_message_instant("Iris", "IDE 제어면이 아직 준비되지 않았습니다.")
            return
        try:
            from iris.system.project_ops import (
                default_generated_rel_path,
                extract_first_code_block,
                is_run_request,
            )

            block = extract_first_code_block(assistant_text)
            if not block:
                return
            profile = load_user_profile(self._db)
            root = (profile.project_root or "").strip()
            if not root:
                self._chat.append_message_instant(
                    "Iris",
                    "외부 IDE에서 실행하려면 먼저 프로필에 project_root를 설정해 주세요.",
                )
                return
            if self._ui_mode != "ide_companion" or not self._get_bound_ide_session(refresh=True):
                opened = surface.registry.invoke("ide.open_folder", {"path": root})
                if not opened.get("ok"):
                    self._chat.append_message_instant(
                        "Iris",
                        f"IDE를 열지 못했습니다: {opened.get('error')}",
                    )
                    return
            rel = default_generated_rel_path(prompt, str(block.get("lang") or ""))
            written = surface.registry.invoke(
                "project.write_file",
                {
                    "project_root": root,
                    "rel_path": rel,
                    "content": str(block.get("code") or ""),
                    "open": True,
                },
            )
            if not written.get("ok"):
                self._chat.append_message_instant(
                    "Iris",
                    f"IDE에 파일을 쓰지 못했습니다: {written.get('error')}",
                )
                return
            if not is_run_request(prompt):
                self._chat.append_message_instant("Iris", f"IDE에 `{rel}` 파일을 열었습니다.")
                return
            ran = surface.registry.invoke(
                "project.run",
                {"project_root": root, "file": rel, "reveal_terminal": True},
            )
            result = ran.get("result") if isinstance(ran.get("result"), dict) else {}
            summary = result.get("summary") or ran.get("error") or "실행 요청을 보냈습니다."
            self._chat.append_message_instant("Iris", f"IDE 터미널 실행: {summary}")
        except Exception as exc:  # noqa: BLE001
            self._chat.append_message_instant("Iris", f"IDE 실행 연결 실패: {exc}")

    def _ensure_voice_runtime(self) -> bool:
        try:
            self._voice_runtime.set_base_url(self._voice_prefs.voice_runtime_url)
            status = self._voice_runtime.ensure_started(
                mock_mode=self._voice_prefs.voice_runtime_mock
            )
            self._tts_runtime_ready = bool(status.running)
            self._status_header.set_tts_status("READY")
            if status.running:
                self._request_tts_warmup()
            return status.running
        except Exception as exc:  # noqa: BLE001
            self._tts_runtime_ready = False
            self._status_header.set_tts_status("ERROR")
            self._live_activity.append_instant_line(
                f"Voice runtime 오류: {exc} (메인 앱은 계속 사용 가능)"
            )
            return False

    def _schedule_tts_runtime_bootstrap(self, *, force: bool = False) -> None:
        if self._test_mode or (not self._voice_prefs.tts_enabled and not force):
            return
        model = (self._voice_prefs.tts_model or "").strip()
        if not model:
            return
        engine = (self._voice_prefs.tts_engine or "qwen").strip().lower()
        runtime_url = self._voice_prefs.voice_runtime_url
        mock_mode = bool(self._voice_prefs.voice_runtime_mock)
        if self._tts_bootstrap_worker is not None:
            return
        if self._tts_runtime_ready:
            if engine in {"qwen", "qwen_custom"}:
                self._request_tts_warmup()
            return
        self._voice_runtime.set_base_url(runtime_url)
        worker = TTSRuntimeBootstrapWorker(
            runtime=self._voice_runtime,
            runtime_url=runtime_url,
            model_name=model,
            mock_mode=mock_mode,
            warmup=engine in {"qwen", "qwen_custom"},
            parent=self,
        )
        self._tts_bootstrap_worker = worker
        worker.finished_ok.connect(
            lambda result, m=model, u=runtime_url, mock=mock_mode: self._on_tts_bootstrap_done(
                result, m, u, mock
            )
        )
        worker.failed.connect(
            lambda err, m=model, u=runtime_url, mock=mock_mode: self._on_tts_bootstrap_failed(
                err, m, u, mock
            )
        )
        worker.finished.connect(
            lambda w=worker, m=model, u=runtime_url, mock=mock_mode: self._on_tts_bootstrap_thread_finished(
                w, m, u, mock
            )
        )
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _bootstrap_matches_current(self, model: str, runtime_url: str, mock_mode: bool) -> bool:
        return (
            model == (self._voice_prefs.tts_model or "").strip()
            and runtime_url == self._voice_prefs.voice_runtime_url
            and mock_mode == bool(self._voice_prefs.voice_runtime_mock)
        )

    def _on_tts_bootstrap_done(
        self, result: object, model: str, runtime_url: str, mock_mode: bool
    ) -> None:
        self._tts_bootstrap_worker = None
        if not self._bootstrap_matches_current(model, runtime_url, mock_mode):
            self._tts_runtime_ready = False
            self._schedule_tts_runtime_bootstrap()
            return
        payload = result if isinstance(result, dict) else {}
        self._tts_runtime_ready = bool(payload.get("running"))
        if payload.get("accepted"):
            self._tts_warmup_model = model
            backend = str(payload.get("stream_backend") or "runtime")
            self._live_activity.append_instant_line(f"TTS runtime warmup scheduled ({backend})")
        self._resume_queued_tts_after_bootstrap()

    def _on_tts_bootstrap_failed(
        self, err: str, model: str, runtime_url: str, mock_mode: bool
    ) -> None:
        self._tts_bootstrap_worker = None
        self._tts_runtime_ready = False
        if not self._bootstrap_matches_current(model, runtime_url, mock_mode):
            self._schedule_tts_runtime_bootstrap()
            return
        self._live_activity.append_instant_line(f"TTS runtime warmup skipped: {err[:160]}")
        self._resume_queued_tts_after_bootstrap()

    def _on_tts_bootstrap_thread_finished(
        self,
        worker: TTSRuntimeBootstrapWorker,
        model: str,
        runtime_url: str,
        mock_mode: bool,
    ) -> None:
        if worker is not self._tts_bootstrap_worker or not worker.isInterruptionRequested():
            return
        self._tts_bootstrap_worker = None
        self._tts_runtime_ready = False
        if not self._bootstrap_matches_current(model, runtime_url, mock_mode):
            self._schedule_tts_runtime_bootstrap()

    def _resume_queued_tts_after_bootstrap(self) -> None:
        if not self._tts_queue or self._tts_pcm_job_id == self._tts_job_id:
            return
        if not self._tts_runtime_ready or not self._tts_can_start(self._tts_active_msg_id):
            self._tts_queue = []
            self._tts_input_finished = True
            self._maybe_end_pcm_session()
            return
        self._tts_pcm_job_id = self._tts_job_id
        self._tts_pcm_ending = False
        self._start_next_tts_segment()

    def _request_tts_warmup(self) -> None:
        if self._voice_prefs.voice_runtime_mock:
            return
        if (self._voice_prefs.tts_engine or "qwen").strip().lower() not in {"qwen", "qwen_custom"}:
            return
        model = (self._voice_prefs.tts_model or "").strip()
        if not model or model == self._tts_warmup_model:
            return
        if self._tts_warmup_worker is not None and self._tts_warmup_worker.isRunning():
            return
        worker = TTSWarmupWorker(
            runtime_url=self._voice_prefs.voice_runtime_url,
            model_name=model,
            parent=self,
        )
        self._tts_warmup_worker = worker
        worker.finished_ok.connect(lambda result, m=model: self._on_tts_warmup_done(result, m))
        worker.failed.connect(lambda err: self._on_tts_warmup_failed(err))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_tts_warmup_done(self, result: object, model: str) -> None:
        self._tts_warmup_worker = None
        payload = result if isinstance(result, dict) else {}
        if not payload.get("accepted"):
            return
        self._tts_warmup_model = model
        backend = str(payload.get("stream_backend") or "runtime")
        self._live_activity.append_instant_line(f"TTS warmup scheduled ({backend})")

    def _on_tts_warmup_failed(self, err: str) -> None:
        self._tts_warmup_worker = None
        self._live_activity.append_instant_line(f"TTS warmup skipped: {err[:160]}")

    def _set_mic_recording(self, recording: bool) -> None:
        self._mic_listen_active = recording
        self._drag.set_mic_recording(recording)
        self._chat.set_mic_recording(recording)

    def _build_aloha_learner(self) -> AlohaLearner:
        prefs = getattr(self, "_learning_prefs", None) or load_learning_preferences(self._db)
        model = prefs.vlm_model or (self._settings.ollama_model or "").strip()
        provider = prefs.vlm_provider or "auto"
        if provider == "auto":
            provider = "ollama"
        return AlohaLearner(
            api_provider=provider,
            ollama_model=model if provider == "ollama" else prefs.vlm_model,
            openai_model=prefs.api_fallback_model or "gpt-4o",
            claude_model=prefs.api_fallback_model or "claude-sonnet-4-20250514",
            ollama_base_url=self._settings.ollama_base_url,
        )

    def _iris_learning_hwnds(self) -> list[int]:
        try:
            wid = int(self.winId())
            return [wid] if wid else []
        except Exception:
            return []

    def _on_learning_state(self, state: LearningState) -> None:
        self._drag.set_learning_state(state)

    def _on_learning_toggle(self) -> None:
        """학습 아이콘만으로 시작/종료 — 채팅 명령 없음."""
        st = self._learning.state
        if st == LearningState.PROCESSING:
            return
        if st == LearningState.IDLE:
            QTimer.singleShot(0, self._start_learning_session)
            return
        if st == LearningState.RECORDING:
            self._stop_learning_session()
            return
        if st == LearningState.ERROR:
            self._learning.recover_to_idle()

    def _resolve_learning_vlm_or_guide(self) -> bool:
        """True면 녹화 시작 진행. False면 취소."""
        prefs = self._learning_prefs
        client = OllamaClient(self._settings.ollama_base_url)
        current = (prefs.vlm_model or self._settings.ollama_model or "").strip()
        verdict = evaluate_ollama_model(client, current)

        # prefs에 API fallback이 명시되고 ollama가 실패면 API 평가
        keys = _load_vlm_keys()
        if not verdict.ok and prefs.api_fallback_provider and prefs.api_fallback_model:
            has = bool(
                keys.get("OPENAI_API_KEY")
                or keys.get("IRIS_OPENAI_API_KEY")
                or keys.get("ANTHROPIC_API_KEY")
                or keys.get("IRIS_ANTHROPIC_API_KEY")
            )
            api_v = evaluate_api_fallback(
                prefs.api_fallback_provider, prefs.api_fallback_model, has_key=has
            )
            if api_v.ok:
                self._learning.set_learner(
                    AlohaLearner(
                        api_provider=api_v.provider,
                        openai_model=api_v.model,
                        claude_model=api_v.model,
                        ollama_base_url=self._settings.ollama_base_url,
                    )
                )
                self._learning.set_record_only(False)
                return True

        if verdict.ok:
            self._learning.set_learner(
                AlohaLearner(
                    api_provider="ollama",
                    ollama_model=verdict.model,
                    ollama_base_url=self._settings.ollama_base_url,
                )
            )
            self._learning.set_record_only(False)
            prefs.vlm_provider = "ollama"
            prefs.vlm_model = verdict.model
            self._learning_prefs = prefs
            save_learning_preferences(self._db, prefs)
            return True

        # 안내 다이얼로그
        ollama_opts = [
            (m.name, reason) for m, reason in list_learning_vlm_models(client)
        ]
        api_opts: list[tuple[str, str, str]] = []
        if keys.get("OPENAI_API_KEY") or keys.get("IRIS_OPENAI_API_KEY"):
            api_opts.append(("openai", "gpt-4o", "gpt-4o (OpenAI Vision)"))
            api_opts.append(("openai", "gpt-4.1", "gpt-4.1 (OpenAI Vision)"))
        if keys.get("ANTHROPIC_API_KEY") or keys.get("IRIS_ANTHROPIC_API_KEY"):
            api_opts.append(
                ("anthropic", "claude-sonnet-4-20250514", "Claude Sonnet (Vision)")
            )

        dlg = VlmGuideDialog(
            verdict=verdict,
            ollama_options=ollama_opts,
            api_options=api_opts,
            parent=self,
        )
        if not dlg.exec():
            return False
        choice = dlg.choice()
        if choice == VlmGuideDialog.RESULT_CANCEL:
            return False
        if choice == VlmGuideDialog.RESULT_RECORD_ONLY:
            self._learning.set_record_only(True)
            self._live_activity.append_instant_line(
                "VLM 없이 녹화만 진행합니다 (pending_vlm)."
            )
            return True
        # USE_VLM
        provider = dlg.selected_provider()
        model = dlg.selected_model()
        prefs.vlm_provider = provider
        prefs.vlm_model = model
        if provider in {"openai", "anthropic"}:
            prefs.api_fallback_provider = provider
            prefs.api_fallback_model = model
        self._learning_prefs = prefs
        save_learning_preferences(self._db, prefs)
        self._learning.set_learning_prefs(prefs)
        self._learning.set_learner(
            AlohaLearner(
                api_provider=provider,
                ollama_model=model if provider == "ollama" else "",
                openai_model=model if provider == "openai" else "gpt-4o",
                claude_model=model if provider in {"anthropic", "claude"} else "",
                ollama_base_url=self._settings.ollama_base_url,
            )
        )
        self._learning.set_record_only(False)
        return True

    def _start_learning_session(self) -> None:
        if self._learning.state != LearningState.IDLE:
            return
        # E: 훅 진단
        probe = probe_input_hooks()
        if not probe.ok:
            from PyQt6.QtWidgets import QMessageBox

            msg = QMessageBox(self)
            msg.setWindowTitle("입력 관찰 불가")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText("마우스/키보드 훅을 시작할 수 없습니다.")
            msg.setInformativeText(
                "\n".join(
                    [
                        *probe.messages[:3],
                        "",
                        probe.security_hint,
                        probe.accessibility_hint,
                        probe.elevation_hint,
                        "",
                        "설정 → 권한에서 진단/권한 수준을 확인하세요.",
                    ]
                )
            )
            msg.exec()
            return

        pol = policy_for(self._learning_prefs.permission_level)
        if pol.prefer_elevation:
            from iris.learning.permission import is_process_elevated

            if not is_process_elevated():
                self._live_activity.append_instant_line(request_elevation_hint())

        if not self._resolve_learning_vlm_or_guide():
            return

        try:
            self._learning.set_learning_prefs(self._learning_prefs)
            self._learning.start_recording()
        except Exception as exc:
            self._learning.mark_error(str(exc))
            QTimer.singleShot(1800, self._learning.recover_to_idle)

    def _stop_learning_session(self) -> None:
        if self._learning.state != LearningState.RECORDING:
            return
        self._learning.stop_hooks_immediately()
        self._learning.mark_processing()
        if self._learning_worker is not None and self._learning_worker.isRunning():
            return
        worker = LearningProcessWorker(self._learning, parent=self)
        self._learning_worker = worker
        worker.finished_ok.connect(self._on_learning_finished)
        worker.failed.connect(self._on_learning_failed)
        worker.start()

    def _on_learning_finished(self, result: object) -> None:
        self._learning_worker = None
        payload = result if isinstance(result, dict) else {}
        self._learning.mark_success(payload)
        self._sync_learning_wiki()

    def _on_learning_failed(self, err: str) -> None:
        self._learning_worker = None
        self._learning.mark_error(err)
        QTimer.singleShot(1800, self._learning.recover_to_idle)

    def _sync_learning_wiki(self) -> None:
        """학습된 업무 목록을 Iris Wiki user/learning/workflows.md 에 반영."""
        try:
            wfs = self._learning.list_learned_workflows()
            rows = [
                {
                    "id": str(w.id),
                    "name": w.name,
                    "summary": w.summary,
                    "status": w.status,
                    "primary_apps": w.primary_apps,
                    "created_at": w.created_at,
                    "trace_id": w.trace_id,
                }
                for w in wfs
            ]
            self._iris_wiki.sync_learned_workflows(rows)
        except Exception as exc:  # noqa: BLE001
            self._live_activity.append_instant_line(f"Wiki 학습 동기화 스킵: {str(exc)[:80]}")

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
        self._tts_job_id += 1
        self._tts_pump_timer.stop()
        self._tts_pump = None
        self._tts_input_finished = True
        self._tts_stream_had_content = False
        self._tts_queue = []
        self._tts_active_play = False
        self._tts_pcm_ending = False
        self._tts_pcm_job_id = None
        if self._tts_active_msg_id:
            self._chat.set_speaker_status(self._tts_active_msg_id, "idle")
        self._tts_active_msg_id = ""
        self._tts_stopping = True
        try:
            self._media_player.stop()
            self._pcm_player.stop()
        except Exception:
            pass
        finally:
            self._tts_stopping = False
        self._resume_mic_after_tts()
        worker, self._tts_worker = self._tts_worker, None
        if worker is not None and worker.isRunning():
            try:
                worker.request_cancel()
            except Exception:
                pass
            self._tts_cancelled_workers.append(worker)
        self._status_header.set_tts_status("READY" if self._voice_prefs.tts_enabled else "OFF")

    def _release_cancelled_tts_worker(self, worker: TTSStreamWorker) -> None:
        try:
            self._tts_cancelled_workers.remove(worker)
        except ValueError:
            pass

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

        # Manual replay keeps the complete answer together for the original prosody.
        normed = normalize_tts_text(text, mapping)
        normed = (normed or "").strip()
        if not normed:
            return
        max_chars = max(1, len(normed))
        cleaned = split_tts_sentences(
            normed,
            max_chars=max_chars,
            first_max_chars=max_chars,
        )
        if not cleaned:
            return
        self._tts_perf = {
            "response_start": time.perf_counter(),
            "tts_first_clause_ready": time.perf_counter(),
        }
        self._tts_perf_logged = False
        self._tts_pump_timer.stop()
        self._tts_pump = None
        self._tts_input_finished = True
        self._tts_stream_had_content = False
        if not self._tts_can_start(msg_id):
            return
        self._stop_tts_playback()
        self._tts_input_finished = True
        self._tts_active_msg_id = msg_id
        self._tts_pcm_job_id = self._tts_job_id
        self._tts_pcm_ending = False
        self._chat.set_speaker_status(msg_id, "busy")
        self._tts_queue = cleaned
        if not self._tts_runtime_ready:
            self._set_tts_orb_warmup(True)
            self._status_header.set_tts_status("BUSY")
            self._schedule_tts_runtime_bootstrap(force=True)
            return
        self._start_next_tts_segment()

    def _tts_can_start(self, msg_id: str) -> bool:
        engine = (self._voice_prefs.tts_engine or "qwen").strip().lower()
        if engine == "qwen_custom" and not (self._voice_prefs.tts_custom_model_path or "").strip():
            self._live_activity.append_instant_line(
                "Qwen 파인튜닝 경로가 비어 있습니다. 설정에서 custom checkpoint를 지정하세요."
            )
            return False
        if engine == "gpt_sovits":
            if not (self._voice_prefs.gpt_sovits_url or "").strip():
                self._live_activity.append_instant_line("GPT-SoVITS URL이 비어 있습니다.")
                return False
        elif not self._voice_prefs.tts_use_voice_profile:
            ref_audio = self._voice_prefs.tts_reference_audio
            ref_text = self._voice_prefs.tts_reference_text
            if not ref_audio or not ref_text:
                self._live_activity.append_instant_line("TTS 기준 음성이 아직 설정되지 않았습니다.")
                return False
            if not Path(ref_audio).is_file():
                self._live_activity.append_instant_line(f"기준 음성 파일이 없습니다: {ref_audio}")
                if msg_id:
                    self._chat.set_speaker_status(msg_id, "error")
                return False
        return True

    def _append_tts_chunks(self, chunks: list[str]) -> None:
        if not chunks:
            return
        self._mark_tts_perf("tts_first_clause_ready")
        msg_id = self._tts_active_msg_id
        live = self._tts_pcm_job_id == self._tts_job_id
        if not live:
            if self._tts_bootstrap_worker is not None or not self._tts_runtime_ready:
                self._tts_queue.extend(chunks)
                self._set_tts_orb_warmup(True)
                self._status_header.set_tts_status("BUSY")
                self._schedule_tts_runtime_bootstrap()
                return
            if not self._tts_can_start(msg_id):
                return
            self._tts_active_msg_id = msg_id
            self._tts_pcm_job_id = self._tts_job_id
            self._tts_pcm_ending = False
            if msg_id:
                self._chat.set_speaker_status(msg_id, "busy")
        self._tts_queue.extend(chunks)
        self._start_next_tts_segment()

    def _tts_busy(self) -> bool:
        return self._tts_worker is not None and self._tts_worker.isRunning()

    def _tts_stream_payload(self) -> dict:
        use_profile = self._voice_prefs.tts_use_voice_profile
        return {
            "voice_prompt_hash": "" if use_profile else self._voice_prefs.tts_voice_prompt_hash,
            "tts_model_name": self._voice_prefs.tts_model,
            "tone": None if self._voice_prefs.tts_tone_routing else "neutral",
            "engine": self._voice_prefs.tts_engine or "qwen",
            "custom_speaker": self._voice_prefs.tts_custom_speaker or "iris",
            "custom_model_path": self._voice_prefs.tts_custom_model_path,
            "gpt_sovits_url": self._voice_prefs.gpt_sovits_url,
            "voice_data_dir": self._voice_prefs.voice_data_dir,
            "tone_routing": self._voice_prefs.tts_tone_routing,
        }

    def _set_tts_orb_warmup(self, active: bool) -> None:
        """TTS BUSY 구간만 구체를 조금 더 살아있게 하고 상태 점프는 피한다."""
        try:
            self._viz.particle_core().set_activity_level(1.18 if active else 1.0)
        except Exception:
            pass

    def _start_next_tts_segment(self) -> None:
        if not should_start_tts_synth(
            synthesizing=self._tts_busy(),
            pending_count=len(self._tts_queue),
        ):
            self._maybe_end_pcm_session()
            return
        use_profile = self._voice_prefs.tts_use_voice_profile
        engine = (self._voice_prefs.tts_engine or "qwen").strip().lower()
        text = self._tts_queue.pop(0)
        if not self._tts_active_play:
            self._set_tts_orb_warmup(True)
            self._status_header.set_tts_status("BUSY")
            if self._tts_active_msg_id:
                self._chat.set_speaker_status(self._tts_active_msg_id, "busy")
        job_id = self._tts_job_id
        payload = self._tts_stream_payload()
        if engine == "qwen" and not use_profile and not payload.get("voice_prompt_hash"):
            payload["_prepare_ref_audio"] = self._voice_prefs.tts_reference_audio
            payload["_prepare_ref_text"] = self._voice_prefs.tts_reference_text
        worker = TTSStreamWorker(
            runtime_url=self._voice_prefs.voice_runtime_url,
            text=text,
            payload=payload,
            parent=self,
        )
        self._tts_worker = worker
        worker.prepared.connect(lambda voice_hash, j=job_id: self._on_tts_voice_prepared(voice_hash, j))
        worker.started_fmt.connect(lambda rate, j=job_id: self._on_pcm_format(rate, j))
        worker.chunk.connect(lambda pcm, j=job_id: self._on_pcm_chunk(pcm, j))
        worker.finished_ok.connect(lambda j=job_id: self._on_tts_stream_finished(j))
        worker.failed.connect(lambda err, j=job_id: self._on_tts_failed(err, j))
        worker.finished.connect(lambda w=worker: self._release_cancelled_tts_worker(w))
        worker.finished.connect(worker.deleteLater)
        self._mark_tts_perf("tts_request_start")
        worker.start()

    def _on_tts_voice_prepared(self, voice_hash: str, job_id: int) -> None:
        if job_id != self._tts_job_id:
            return
        if not voice_hash:
            self._on_tts_failed("TTS voice prompt 준비에 실패했습니다.", job_id)
            return
        self._voice_prefs.tts_voice_prompt_hash = voice_hash
        save_voice_preferences(self._db, self._voice_prefs)

    def _on_pcm_format(self, sample_rate: int, job_id: int) -> None:
        if job_id != self._tts_job_id:
            return
        self._pcm_player.set_format(sample_rate)

    def _on_pcm_chunk(self, pcm: bytes, job_id: int) -> None:
        if job_id != self._tts_job_id:
            return
        self._mark_tts_perf("tts_first_pcm")
        self._pcm_player.set_volume(self._voice_prefs.tts_volume)
        self._pcm_player.feed(pcm)

    def _on_pcm_speakers_opened(self) -> None:
        if self._tts_pcm_job_id != self._tts_job_id:
            return
        self._mark_tts_perf("speaker_open")
        if self._mic_listen_active:
            self._recorder.set_capture_paused(True)
        self._tts_active_play = True
        self._status_header.set_tts_status("SPEAK")
        if self._tts_active_msg_id:
            self._chat.set_speaker_status(self._tts_active_msg_id, "playing")

    def _on_pcm_drained(self) -> None:
        if self._tts_stopping or self._tts_pcm_job_id != self._tts_job_id:
            return
        self._tts_active_play = False
        if not self._tts_pcm_ending:
            if self._tts_busy() or self._tts_queue:
                if self._tts_active_msg_id:
                    self._chat.set_speaker_status(self._tts_active_msg_id, "busy")
                self._status_header.set_tts_status("BUSY")
            return
        self._mark_tts_perf("audio_drained")
        self._finish_tts_playback()

    def _resume_mic_after_tts(self) -> None:
        if self._mic_listen_active and (self._stt_worker is None or not self._stt_worker.isRunning()):
            self._recorder.set_capture_paused(False)

    def _maybe_end_pcm_session(self) -> None:
        if (
            not self._tts_input_finished
            or self._tts_busy()
            or self._tts_queue
            or self._tts_pcm_ending
        ):
            return
        self._mark_tts_perf("tts_generation_finished")
        if self._tts_pcm_job_id != self._tts_job_id:
            self._finish_tts_playback()
            return
        self._tts_pcm_ending = True
        self._pcm_player.end_session()

    def _finish_tts_playback(self) -> None:
        self._tts_active_play = False
        self._tts_pcm_ending = False
        self._set_tts_orb_warmup(False)
        if self._tts_active_msg_id:
            self._chat.set_speaker_status(self._tts_active_msg_id, "idle")
        self._status_header.set_tts_status("READY" if self._voice_prefs.tts_enabled else "OFF")
        self._resume_mic_after_tts()
        self._log_tts_perf()

    def _mark_tts_perf(self, name: str) -> None:
        if name not in self._tts_perf:
            self._tts_perf[name] = time.perf_counter()

    def _log_tts_perf(self) -> None:
        if self._tts_perf_logged:
            return
        started = self._tts_perf.get("response_start")
        if started is None:
            return
        self._tts_perf_logged = True

        def elapsed(name: str) -> float | None:
            point = self._tts_perf.get(name)
            return None if point is None else point - started

        def interval(end: str, begin: str) -> float | None:
            end_at = self._tts_perf.get(end)
            begin_at = self._tts_perf.get(begin)
            return None if end_at is None or begin_at is None else end_at - begin_at

        values = {
            "LLM_TTFT": elapsed("llm_first_content"),
            "clause_ready": elapsed("tts_first_clause_ready"),
            "tts_first_pcm": elapsed("tts_first_pcm"),
            "speaker_open": elapsed("speaker_open"),
            "TTS_TTFA": interval("tts_first_pcm", "tts_request_start"),
            "speaker_TTFA": interval("speaker_open", "tts_request_start"),
            "llm_finished": elapsed("llm_finished"),
            "tts_generation": interval("tts_generation_finished", "tts_request_start"),
            "audio_drained": interval("audio_drained", "tts_request_start"),
        }
        metrics = " ".join(
            f"{name}={value:.2f}s" for name, value in values.items() if value is not None
        )
        self._live_activity.append_instant_line(f"[TTS PERF] {metrics or 'no PCM'}")

    def _on_pcm_failed(self, err: str) -> None:
        self._live_activity.append_instant_line(f"TTS 재생 오류: {err}")

    def _on_media_playback_state(self, state: object) -> None:
        from PyQt6.QtMultimedia import QMediaPlayer as _MP
        if state == _MP.PlaybackState.StoppedState:
            self._on_media_finished()

    def _on_media_finished(self) -> None:
        if self._tts_stopping or self._tts_pcm_job_id is not None:
            return
        self._tts_active_play = False
        if self._tts_busy() or self._tts_queue:
            if self._tts_active_msg_id:
                self._chat.set_speaker_status(self._tts_active_msg_id, "busy")
            self._status_header.set_tts_status("BUSY")
            return
        self._maybe_end_pcm_session()

    def _on_tts_stream_finished(self, job_id: int | None = None) -> None:
        if job_id is not None and job_id != self._tts_job_id:
            return
        self._tts_worker = None
        # A short clause may not reach START_MS by itself.  Open the same PCM
        # session now; next synthesis still starts immediately below.
        self._pcm_player.flush_start()
        self._start_next_tts_segment()
        self._maybe_end_pcm_session()

    def _on_tts_failed(self, err: str, job_id: int | None = None) -> None:
        if job_id is not None and job_id != self._tts_job_id:
            return
        worker, self._tts_worker = self._tts_worker, None
        self._tts_job_id += 1
        if worker is not None and worker.isRunning():
            try:
                worker.request_cancel()
            except Exception:
                pass
            self._tts_cancelled_workers.append(worker)
        self._tts_queue = []
        self._tts_input_finished = True
        self._tts_pump = None
        self._tts_pump_timer.stop()
        self._tts_active_play = False
        self._tts_pcm_ending = False
        self._tts_pcm_job_id = None
        self._tts_runtime_ready = False
        self._set_tts_orb_warmup(False)
        self._media_player.stop()
        self._pcm_player.stop()
        self._resume_mic_after_tts()
        self._status_header.set_tts_status("ERROR")
        if self._tts_active_msg_id:
            self._chat.set_speaker_status(self._tts_active_msg_id, "error")
        self._live_activity.append_instant_line(f"TTS 오류: {err}")
        self._chat.fallback_typing_if_waiting_for_tts()

    def _on_chat_failed(self, err: str) -> None:
        if self._ignore_chat_result:
            self._ignore_chat_result = False
            self._chat_worker = None
            self._busy = False
            self._chat.set_generating(False)
            self._stop_tts_playback()
            self._tts_pump = None
            self._api_fallback_pending = False
            return
        # 커스텀 API 직접 호출 실패 → Hermes online이면 1회 폴백
        if self._try_hermes_fallback_after_api_fail(err):
            return
        self._stop_tts_playback()
        self._tts_pump = None
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
        self._chat.set_generating(False)
        self._chat_worker = None
        self._api_fallback_pending = False
        self._state.set_state(AppState.ERROR)
        self._maybe_refresh_ollama_quota()
        QTimer.singleShot(800, lambda: self._state.set_state(AppState.IDLE))

    def _try_hermes_fallback_after_api_fail(self, err: str) -> bool:
        """직접 API 실패 시 Hermes 경유 재시도. 처리했으면 True."""
        if not self._api_fallback_pending:
            return False
        self._api_fallback_pending = False
        if not self._settings.hermes_enabled or not self._hermes_online:
            return False
        model = (self._api_fallback_model or "").strip()
        if not model:
            return False
        if getattr(self._chat, "_stream_active", False):
            self._chat.end_stream_message(None)
        self._live_activity.append_instant_line(
            f"API 직접 호출 실패 → Hermes 폴백: {err[:120]}"
        )
        self._stop_tts_playback()
        self._begin_auto_tts_response()
        self._chat_worker = None
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
        return True

    def _on_app_state(self, state: object) -> None:
        if isinstance(state, AppState):
            self._status_header.set_app_state(state)
            self._viz.set_state(state)

    def _on_metrics_snapshot(self, snapshot: object) -> None:
        self._left_sidebar.utility.metrics.apply_snapshot(snapshot)

    def _on_api_quotas(self, quotas: object) -> None:
        # 부분 갱신(Ollama만)이어도 SERP/FIRE 행이 사라지지 않게 머지
        from iris.infrastructure.api_quota import ApiQuota

        if isinstance(quotas, list):
            for q in quotas:
                if isinstance(q, ApiQuota):
                    self._quota_by_key[q.key] = q
        merged = list(self._quota_by_key.values())
        self._left_sidebar.utility.metrics.apply_quotas(merged)

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

    def _on_calendar_icon(self) -> None:
        self._workspace_mode = "calendar"
        self._workspace_stack.setCurrentWidget(self._calendar_page)
        self._left_sidebar.set_workspace_mode("assistant")
        self._set_workspace_icon_active("calendar")
        self._viz.hide()
        self._orb_spacer.hide()
        self._reload_calendar_month()
        self._refresh_calendar_holidays()
        self._check_calendar_reminders()

    def _sync_calendar_wiki(self) -> None:
        from iris.storage.calendar_events import events_as_dicts, list_events

        self._iris_wiki.sync_schedule_markdown(events_as_dicts(list_events(self._db)))

    def _reload_calendar_month(self) -> None:
        from iris.storage.calendar_events import list_events

        page = self._calendar_page
        events = list_events(self._db, year=page.year, month=page.month)
        page.set_events(events)
        self._sync_calendar_wiki()

    def _refresh_calendar_holidays(self) -> None:
        from iris.infrastructure.kr_holiday_client import holidays_for_year

        year = self._calendar_page.year
        key = self._settings.data_go_kr_service_key
        if not key:
            self._calendar_page.set_holidays(
                [],
                "공휴일 API 키 없음 — .env 에 IRIS_DATA_GO_KR_SERVICE_KEY 추가 후 재시작 "
                "(data.go.kr 한국천문연구원 특일정보)",
            )
            return
        try:
            holidays = holidays_for_year(year, key, force=True)
            self._calendar_page.set_holidays(
                holidays,
                f"대한민국 공휴일 {year}년 · {len(holidays)}건 (공공데이터포털)",
            )
        except Exception as exc:
            from iris.infrastructure.kr_holiday_client import load_cached_holidays

            cached = load_cached_holidays(year) or []
            self._calendar_page.set_holidays(
                cached,
                f"공휴일 갱신 실패 — 캐시 {len(cached)}건 표시: {exc}",
            )

    def _on_calendar_month_changed(self, year: int, month: int) -> None:
        self._reload_calendar_month()
        # 연도가 바뀌면 공휴일도 해당 연도로
        self._refresh_calendar_holidays()

    def _on_calendar_add_event(self, title: str, start: str, note: str, place: str) -> None:
        from iris.infrastructure.calendar_agent import normalize_start_at
        from iris.storage.calendar_events import add_event

        try:
            start_at = normalize_start_at(start)
            add_event(
                self._db,
                title=title,
                start_at=start_at,
                note=note,
                place=place,
            )
            self._reload_calendar_month()
            self._notes.add_note(f"일정 추가: {title}")
        except Exception as exc:
            self._notes.add_note(f"일정 추가 실패: {exc}")

    def _on_calendar_delete_event(self, event_id: int) -> None:
        from iris.storage.calendar_events import delete_event

        if delete_event(self._db, event_id):
            self._reload_calendar_month()
            self._notes.add_note(f"일정 삭제: #{event_id}")

    def _apply_calendar_ops(self, ops: list[dict]) -> list[str]:
        from iris.infrastructure.calendar_agent import normalize_start_at
        from iris.storage.calendar_events import add_event, delete_event, list_events

        notes: list[str] = []
        for op in ops:
            kind = str(op.get("op") or "").strip().lower()
            if kind == "add":
                title = str(op.get("title") or "").strip()
                start = str(op.get("start_at") or "").strip()
                if not title or not start:
                    notes.append("일정 추가 실패: title/start_at 필요")
                    continue
                try:
                    end_raw = str(op.get("end_at") or "").strip()
                    ev = add_event(
                        self._db,
                        title=title,
                        start_at=normalize_start_at(start),
                        end_at=normalize_start_at(end_raw) if end_raw else "",
                        note=str(op.get("note") or "").strip(),
                        place=str(op.get("place") or "").strip(),
                    )
                    notes.append(f"추가됨: {ev.title} ({ev.start_at})")
                except Exception as exc:
                    notes.append(f"추가 실패: {exc}")
            elif kind == "delete":
                try:
                    eid = int(op.get("id"))
                except (TypeError, ValueError):
                    notes.append("삭제 실패: id 필요")
                    continue
                if delete_event(self._db, eid):
                    notes.append(f"삭제됨: #{eid}")
                else:
                    notes.append(f"삭제 대상 없음: #{eid}")
            elif kind == "list":
                events = list_events(self._db)
                if not events:
                    notes.append("등록된 일정 없음")
                else:
                    notes.append(
                        "일정 목록: "
                        + "; ".join(f"#{e.id} {e.start_at} {e.title}" for e in events[:20])
                    )
        if notes:
            self._reload_calendar_month()
        return notes

    def _check_calendar_reminders(self) -> None:
        from datetime import datetime, timedelta

        from iris.storage.calendar_events import list_events, mark_reminded

        now = datetime.now()
        soon_until = now + timedelta(hours=24)
        for ev in list_events(self._db):
            try:
                start = datetime.fromisoformat(ev.start_at)
            except ValueError:
                continue
            if not ev.reminded_overdue and start < now:
                self._notes.try_add_alert(
                    0,
                    "schedule_overdue",
                    "지난 일정",
                    f"{ev.title} ({ev.start_at})",
                    "calendar",
                    event_id=ev.id,
                )
                mark_reminded(self._db, ev.id, overdue=True)
            elif not ev.reminded_soon and now <= start <= soon_until:
                self._notes.try_add_alert(
                    0,
                    "schedule_soon",
                    "다가오는 일정",
                    f"{ev.title} ({ev.start_at})",
                    "calendar",
                    event_id=ev.id,
                )
                mark_reminded(self._db, ev.id, soon=True)

    def _on_calendar_chat_send(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        panel = self._calendar_page.iris_panel
        if self._calendar_busy:
            panel.append_iris_error("이전 요청을 처리 중입니다. 잠시만요.")
            return
        if not self._settings.hermes_enabled:
            panel.append_iris_error(
                "일정 대화는 Hermes 에이전트가 필요합니다. 설정에서 Hermes를 켜 주세요."
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

        from iris.infrastructure.calendar_agent import build_calendar_agent_context
        from iris.infrastructure.kr_holiday_client import load_cached_holidays
        from iris.storage.calendar_events import list_events

        events = list_events(self._db)
        day = self._calendar_page.selected_day.isoformat()
        holiday_names: list[str] = []
        for h in load_cached_holidays(self._calendar_page.year) or []:
            if h.date == day:
                holiday_names.append(h.name)
        context = build_calendar_agent_context(
            events=events,
            selected_day=day,
            holidays=holiday_names,
        )

        panel.append_user(text)
        self._calendar_history.append({"role": "user", "content": text})
        messages = [{"role": "system", "content": context}, *self._calendar_history]

        self._calendar_busy = True
        panel.set_orb_state("PROCESSING")
        worker = HermesChatWorker(
            self._settings.hermes_base_url,
            model,
            messages,
            api_key=self._settings.hermes_api_key,
            command=self._settings.hermes_command,
            parent=self,
        )
        self._calendar_chat_worker = worker
        worker.tool_progress.connect(self._on_calendar_chat_tool)
        worker.content_chunk.connect(self._on_calendar_chat_chunk)
        worker.finished_ok.connect(self._on_calendar_chat_finished)
        worker.failed.connect(self._on_calendar_chat_failed)
        worker.start()

    def _on_calendar_chat_tool(self, message: str) -> None:
        text = (message or "").strip()
        if text:
            self._calendar_page.iris_panel.append_iris_tool(text)
            self._calendar_page.iris_panel.set_orb_state("EXECUTING")

    def _on_calendar_chat_chunk(self, chunk: str) -> None:
        self._calendar_page.iris_panel.set_orb_state("RESPONDING")
        self._calendar_page.iris_panel.append_iris_chunk(chunk)

    def _on_calendar_chat_finished(self, content: str) -> None:
        from iris.infrastructure.calendar_agent import parse_calendar_ops, strip_calendar_ops

        text = (content or "").strip()
        ops = parse_calendar_ops(text)
        visible = strip_calendar_ops(text)
        self._calendar_page.iris_panel.end_iris(visible or None)
        if text:
            self._calendar_history.append({"role": "assistant", "content": text})
        for note in self._apply_calendar_ops(ops):
            self._calendar_page.iris_panel.append_iris_tool(note)
        if not self._hermes_online:
            self._hermes_online = True
            self._status_header.refresh_backend_status(
                self._settings,
                hermes_online=True,
            )
        self._calendar_busy = False
        self._calendar_chat_worker = None
        self._calendar_page.iris_panel.set_orb_state("IDLE")

    def _on_calendar_chat_failed(self, err: str) -> None:
        self._calendar_page.iris_panel.end_iris()
        if self._calendar_history and self._calendar_history[-1].get("role") == "user":
            self._calendar_history.pop()
        self._calendar_page.iris_panel.append_iris_error(f"Hermes 오류: {err[:200]}")
        self._calendar_busy = False
        self._calendar_chat_worker = None
        self._calendar_page.iris_panel.set_orb_state("ERROR")

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
        self._email_page.iris_panel.end_iris(text or None)
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
        """Hermes/Ollama 요청용 — Iris Control MCP 지침 + project_root.

        Hermes 경로는 HERMES_HOME/SOUL.md가 identity(slot #1)라 페르소나를
        여기 넣지 않는다(중복·토큰 낭비). Ollama 직행만 SOUL 원본을 주입한다.
        """
        messages = list(self._history)
        try:
            profile = load_user_profile(self._db)
            root = (profile.project_root or "").strip()
        except Exception:
            root = ""
        bits: list[str] = []
        # ponytail: Hermes는 SOUL.md가 identity. Ollama만 여기 주입.
        if not self._use_hermes_backend():
            try:
                from iris.system.hermes_soul_sync import load_iris_persona_text

                persona = load_iris_persona_text()
            except Exception:
                persona = ""
            if persona:
                bits.append(persona)
        bits.append(
            "Iris Light UI control: for IDE / Companion / open project / 작업 시작, "
            "use MCP tools iris_get_state / iris_get_catalog / iris_invoke "
            "(e.g. iris_invoke action=ide.enter_companion). "
            "Do NOT use terminal cursor/code alone — that skips Companion tiling. "
            "Do NOT invent that Iris has no IDE — Iris controls the preferred IDE via MCP. "
            "Writing code: project.write_file with open=true (opens an empty IDE tab, then streams chunks into the file). "
            "Running code: project.run — output in IDE integrated terminal; summarize only in chat. "
            "When you use ANY web search/browse/fetch tool, the final answer MUST include a "
            "Sources section with markdown links [title](https://url) for each page you relied on. "
            "Never state researched facts without at least one citation link. "
            "Iris UI turns those links into clickable citation chips. "
            "When a product/place/UI is clearer with a picture and you have a direct image URL "
            "(search thumbnail, og image, or page asset), include it inline as "
            "markdown ![short label](https://...png|jpg|gif|webp). "
            "Iris shows those images in the chat; users can click to enlarge.",
        )
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
        if sys.platform == "darwin":
            from iris.automation.window_controller import is_macos_window_number_alive

            return is_macos_window_number_alive(int(hwnd))
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

                title = get_window_title(int(hwnd)) or ""
                # ponytail: generic/Agents 제목은 로딩·셸 — companion/session 유지.
                # 천장: 제목만으로 다른 workspace 판별 → 업그레이드: cwd/CLI 힌트.
                if workspace_title_lost_context(title, session.workspace_root):
                    self._clear_ide_session("다른 workspace로 변경")
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
        """c) workspace_root가 제목에 확실히 포함된 창만. Agents/generic 제외."""
        root_name = Path(workspace_root).name.strip().lower()
        if not root_name:
            return None, None, ""
        wins = list_ide_windows(ide_id, load_user_profile(self._db).ide_exe_path)
        for win in wins:
            title = str(win.get("title") or "").strip()
            low = title.lower()
            if is_cursor_agents_title(title) or is_generic_ide_title(title):
                continue
            if root_name in low:
                return int(win["hwnd"]), int(win["pid"]), title
        return None, None, ""

    def _record_synced_rects(self) -> None:
        """방금 우리가 배치한 IDE/Iris 창 크기를 기억 — 다음 폴링에서 사용자가
        직접 드래그해 달라졌는지 비교하는 기준선."""
        self._last_synced_ide_rect = read_ide_rect(
            self._ide_hwnd or 0, pid=self._ide_pid
        )
        self._last_synced_iris_rect = QRect(self.geometry())

    def _schedule_companion_retile(self, ide_hwnd: int) -> None:
        """Cursor가 자체 레이아웃으로 되돌리는 경우 대비 지연 재타일.

        Iris companion 레이아웃(_ui_mode)은 건드리지 않는다 — tile만 재적용.
        """
        hwnd = int(ide_hwnd)
        pid = self._ide_pid

        def _retile() -> None:
            if self._ui_mode != "ide_companion":
                return
            if not self._ide_hwnd_alive(hwnd):
                return
            # Iris 레이아웃을 풀지 않고 IDE/Iris 좌표만 다시 맞춤
            tile_ide_and_iris(hwnd, self, ide_ratio=0.8, ide_pid=pid)
            self._record_synced_rects()

        QTimer.singleShot(400, _retile)
        QTimer.singleShot(1200, _retile)
        QTimer.singleShot(2500, _retile)

    def _sync_companion_split(self) -> None:
        """IDE/Iris 중 하나가 사용자에 의해 드래그되면 반대쪽을 맞춰 따라가게 한다.

        AXObserver 같은 실시간 알림 대신 짧은 폴링으로 근사— 두 창 다 우리가
        기억한 마지막 값과 비교해 어느 쪽이 바뀌었는지 보고, 바뀐 쪽을 새 경계로
        삼아 나머지를 work area의 남은 영역으로 재계산한다.
        """
        if self._ui_mode != "ide_companion" or not self._ide_hwnd:
            return
        if not self._ide_hwnd_alive(self._ide_hwnd):
            return
        current_ide = read_ide_rect(self._ide_hwnd, pid=self._ide_pid)
        current_iris = QRect(self.geometry())
        if current_ide is None:
            return

        ide_changed = (
            self._last_synced_ide_rect is None or current_ide != self._last_synced_ide_rect
        )
        iris_changed = (
            self._last_synced_iris_rect is None or current_iris != self._last_synced_iris_rect
        )
        if not ide_changed and not iris_changed:
            return

        work = work_area_for(self)
        if ide_changed:
            # IDE 오른쪽 끝을 새 경계로 — Iris는 남은 폭을 채운다.
            iris_left = max(work.left(), min(current_ide.left() + current_ide.width(), work.right()))
            iris_rect = QRect(iris_left, work.top(), work.left() + work.width() - iris_left, work.height())
            place_qt_window(self, iris_rect)
            self._last_synced_ide_rect = current_ide
            self._last_synced_iris_rect = QRect(self.geometry())
        else:
            # Iris 왼쪽 끝을 새 경계로 — IDE는 그 앞까지 채운다.
            ide_width = max(200, current_iris.left() - work.left())
            ide_rect = QRect(work.left(), work.top(), ide_width, work.height())
            place_hwnd(self._ide_hwnd, ide_rect, pid=self._ide_pid)
            self._last_synced_iris_rect = current_iris
            self._last_synced_ide_rect = read_ide_rect(self._ide_hwnd, pid=self._ide_pid)

    def _activate_companion_tile(
        self, hwnd: int, *, label: str = "", pid: int | None = None
    ) -> str:
        """IDE 창이 준비된 뒤: Companion 레이아웃 → 80:20 타일.

        순서: (1) IDE 이미 뜸 (2) Iris 세로 레이아웃 (3) 타일.
        pid: macOS 타일링(Accessibility API)에 필요 — self._ide_pid를 여기서 갱신한다.
        """
        from PyQt6.QtWidgets import QApplication

        self._ide_hwnd = int(hwnd)
        if pid:
            self._ide_pid = int(pid)
        # 1) Iris companion UI (min size 축소 포함)
        self._apply_ide_companion_layout(True)
        QApplication.processEvents()
        # 2) 타일
        ok, tile_err = tile_ide_and_iris(
            self._ide_hwnd, self, ide_ratio=0.8, ide_pid=self._ide_pid
        )
        if not ok:
            self._apply_ide_companion_layout(False)
            return tile_err or "tile failed"
        self._fit_companion_orb_to_width()
        self._viz.request_sync_orb_anchor("ide_companion_tiled")
        self._schedule_companion_retile(self._ide_hwnd)
        self._record_synced_rects()
        if not self._companion_sync_timer.isActive():
            self._companion_sync_timer.start()
        if label:
            self._live_activity.append_instant_line(f"IDE Companion: {label} tiled 80:20")
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
            err2 = self._activate_companion_tile(
                int(session.hwnd), label=f"{ide_id} (bound)", pid=session.pid
            )
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
                err2 = self._activate_companion_tile(
                    int(hwnd2), label=title2 or Path(project_root).name, pid=pid2
                )
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
                for w in list_ide_windows(
                    ide_id, profile.ide_exe_path, include_untitled=True
                )
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
            self._live_activity.append_instant_line("IDE 새 창을 기다리는 중…")
            # processEvents로 UI 응답 유지하며 짧게 대기
            deadline = _time.monotonic() + 4.0
            hwnd = None
            title = ""
            while _time.monotonic() < deadline and hwnd is None:
                QApplication.processEvents()
                hwnd, wait_pid, title = wait_for_new_ide_window(
                    ide_id,
                    ide_exe_path=profile.ide_exe_path,
                    exclude_hwnds=before,
                    title_substr="",
                    timeout_sec=0.35,
                )
                if wait_pid:
                    pid = wait_pid
                if hwnd is not None and is_cursor_agents_title(title):
                    hwnd = None
            if hwnd is None:
                self._live_activity.append_instant_line(
                    "IDE 새 창을 찾지 못했습니다. 설정에서 IDE 경로를 확인한 뒤 다시 시도하세요."
                )
                return

        # 순서 2~3: Companion 레이아웃 + 80:20
        spec = get_ide_spec(ide_id)
        name = spec.name if spec else ide_id
        err2 = self._activate_companion_tile(int(hwnd), label=f"{name} (80:20)", pid=pid)
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
        # b) 이미 bound된 session — 같은 workspace면 즉시 타일
        if (
            session is not None
            and session.ide_id == ide_id
            and session.hwnd is not None
            and session.workspace_root
            and Path(session.workspace_root).resolve() == Path(root_s).resolve()
        ):
            err2 = self._activate_companion_tile(
                int(session.hwnd), label=root.name, pid=session.pid
            )
            if err2:
                return err2
            self._bind_ide_session(
                ide_id=ide_id,
                hwnd=int(session.hwnd),
                pid=session.pid,
                workspace_root=root_s,
                mode="workspace",
                source=source,
            )
            return ""

        # c) workspace 제목이 확실한 기존 창
        if session is None or not (
            session.ide_id == ide_id and session.hwnd is not None and not new_window
        ):
            existing_hwnd, existing_pid, existing_title = self._find_workspace_window(
                ide_id, root_s
            )
            if existing_hwnd is not None:
                err2 = self._activate_companion_tile(
                    int(existing_hwnd),
                    label=existing_title or root.name,
                    pid=existing_pid,
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

        # bound + reuse_window: 기존 창에 폴더 주입 후 즉시 타일
        if session is not None and session.ide_id == ide_id and session.hwnd is not None and not new_window:
            try:
                from iris.automation.ide_input import force_focus_hwnd

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
            err2 = self._activate_companion_tile(
                int(session.hwnd),
                label=root.name,
                pid=launched_pid or session.pid,
            )
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

        before = {
            int(w["hwnd"])
            for w in list_ide_windows(
                ide_id, profile.ide_exe_path, include_untitled=True
            )
        }
        if self._ide_hwnd_alive(self._ide_hwnd):
            before.add(int(self._ide_hwnd))

        self._live_activity.append_instant_line(f"IDE 폴더 여는 중: {root_s}")

        hwnd = None
        pid = None
        title = ""

        # Windows 우선 빠른 경로: GUI exe --new-window <folder> 한 방
        launched_pid, launch_err = open_folder_in_ide(
            ide_id,
            root_s,
            ide_exe_path=profile.ide_exe_path,
            ide_cli_path=profile.ide_cli_path,
            new_window=True,
            reuse_window=False,
        )
        if launch_err:
            self._live_activity.append_instant_line(f"IDE 폴더 열기 실패: {launch_err}")
            return launch_err
        pid = launched_pid or self._ide_pid

        deadline = _time.monotonic() + 3.5
        while _time.monotonic() < deadline and hwnd is None:
            QApplication.processEvents()
            hwnd, wait_pid, title = wait_for_new_ide_window(
                ide_id,
                ide_exe_path=profile.ide_exe_path,
                exclude_hwnds=before,
                title_substr=root.name,
                timeout_sec=0.3,
            )
            if wait_pid:
                pid = wait_pid
            if hwnd is not None and is_cursor_agents_title(title):
                hwnd = None

        # 폴백: 빈 창 → reuse inject (one-shot이 새 hwnd를 안 줄 때만)
        if hwnd is None and new_window:
            before2 = {
                int(w["hwnd"])
                for w in list_ide_windows(
                    ide_id, profile.ide_exe_path, include_untitled=True
                )
            }
            if self._ide_hwnd_alive(self._ide_hwnd):
                before2.add(int(self._ide_hwnd))
            launched_pid, launch_err = launch_ide(
                ide_id,
                ide_exe_path=profile.ide_exe_path,
                ide_cli_path=profile.ide_cli_path,
                project_root="",
                new_window=True,
            )
            if launch_err:
                return launch_err
            pid = launched_pid or pid
            deadline = _time.monotonic() + 3.5
            while _time.monotonic() < deadline and hwnd is None:
                QApplication.processEvents()
                hwnd, wait_pid, title = wait_for_new_ide_window(
                    ide_id,
                    ide_exe_path=profile.ide_exe_path,
                    exclude_hwnds=before2,
                    title_substr="",
                    timeout_sec=0.3,
                )
                if wait_pid:
                    pid = wait_pid
                if hwnd is not None and is_cursor_agents_title(title):
                    hwnd = None
            if hwnd is not None:
                try:
                    from iris.automation.ide_input import force_focus_hwnd

                    force_focus_hwnd(int(hwnd))
                    QApplication.processEvents()
                except Exception:
                    pass
                open_folder_in_ide(
                    ide_id,
                    root_s,
                    ide_exe_path=profile.ide_exe_path,
                    ide_cli_path=profile.ide_cli_path,
                    new_window=False,
                    reuse_window=True,
                )
                # ponytail: 제목 대기 생략 — bind는 workspace_root로, 타일 즉시.

        if hwnd is None:
            return "IDE new window started but window not found"

        # 제목 대기 없이 즉시 Companion 타일 (generic title이어도 session 유지)
        label = title if title and not is_generic_ide_title(title) else root.name
        err2 = self._activate_companion_tile(int(hwnd), label=label, pid=pid)
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
        self._cyberspace_bg.set_orb_above_ui(True)

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
        self._companion_sync_timer.stop()
        self._last_synced_ide_rect = None
        self._last_synced_iris_rect = None
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
                f"Android 에뮬레이터 시작 (PID {proc.pid}) — 부팅 후 adb 연결"
            )
            self._live_activity.append_instant_line(
                "한글은 에뮬 화면 키보드(IME) 사용. PC 키보드는 영문·키이벤트용."
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
            previous_tts_model = self._voice_prefs.tts_model
            previous_tts_mode = self._voice_prefs.tts_mode
            previous_runtime_url = self._voice_prefs.voice_runtime_url
            previous_runtime_mock = self._voice_prefs.voice_runtime_mock
            previous_voice_fx = (
                self._voice_prefs.tts_ai_voice_fx_enabled,
                self._voice_prefs.tts_ai_voice_fx_intensity,
            )
            self._voice_prefs = sel.voice_prefs
            voice_fx_changed = previous_voice_fx != (
                self._voice_prefs.tts_ai_voice_fx_enabled,
                self._voice_prefs.tts_ai_voice_fx_intensity,
            )
            runtime_changed = (
                self._voice_prefs.voice_runtime_url != previous_runtime_url
                or self._voice_prefs.voice_runtime_mock != previous_runtime_mock
            )
            if (
                self._tts_bootstrap_worker is not None
                and (runtime_changed or self._voice_prefs.tts_model != previous_tts_model)
            ):
                self._tts_bootstrap_worker.request_cancel()
            if (
                not self._voice_prefs.tts_enabled
                or self._voice_prefs.tts_mode != previous_tts_mode
                or runtime_changed
                or voice_fx_changed
            ):
                self._stop_tts_playback()
            elif self._voice_prefs.tts_model != previous_tts_model:
                self._tts_warmup_model = ""
            if runtime_changed:
                self._tts_runtime_ready = False
                self._tts_warmup_model = ""
            self._settings.always_listen_speech_rms = self._voice_prefs.stt_speech_rms
            self._chat.set_speech_threshold_rms(self._voice_prefs.stt_speech_rms)
            self._recorder.set_speech_rms(self._voice_prefs.stt_speech_rms)
            self._pcm_player.set_voice_effect(
                enabled=self._voice_prefs.tts_ai_voice_fx_enabled,
                intensity=self._voice_prefs.tts_ai_voice_fx_intensity,
            )
            self._voice_runtime.set_base_url(self._voice_prefs.voice_runtime_url)
            QTimer.singleShot(0, self._schedule_tts_runtime_bootstrap)
            if getattr(sel, "learning_prefs", None) is not None:
                self._learning_prefs = sel.learning_prefs
                self._learning.set_learning_prefs(self._learning_prefs)
                if not self._test_mode:
                    self._learning.set_learner(self._build_aloha_learner())
            self._status_header.set_tts_status(
                "READY" if self._voice_prefs.tts_enabled else "OFF"
            )
            self._saved_model = sel.ollama_model.strip()
            if self._saved_model:
                save_selected_model(self._db, self._saved_model)
            self._status_header.set_model_name(self._settings.model_name or "(unset)")
            self._refresh_hermes_health()
            if (
                self._settings.hermes_enabled
                and self._saved_model
                and not is_api_runtime_model(self._saved_model)
            ):
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
        wiz = getattr(self, "_setup_wizard", None)
        if wiz is not None and wiz.isVisible():
            if not wiz.allow_close():
                event.ignore()
                return
            wiz.abort_and_close()
        try:
            stop_control_surface(self)
            self._pinned_monitor.stop()
            try:
                self._learning.interrupt_on_shutdown()
            except Exception:
                pass
            if self._learning_worker is not None and self._learning_worker.isRunning():
                cancel = getattr(self._learning_worker, "request_cancel", None)
                if callable(cancel):
                    cancel()
                self._learning_worker.wait(2000)
            if self._recorder.is_recording():
                self._recorder.cancel_recording()
            self._stop_tts_playback()
            for worker in list(self._tts_cancelled_workers):
                if worker.isRunning():
                    worker.request_cancel()
                    worker.wait(1500)
            if self._tts_warmup_worker is not None and self._tts_warmup_worker.isRunning():
                self._tts_warmup_worker.wait(1500)
            if self._tts_bootstrap_worker is not None and self._tts_bootstrap_worker.isRunning():
                self._tts_bootstrap_worker.request_cancel()
                self._tts_bootstrap_worker.wait(2000)
            if self._chat_worker is not None and self._chat_worker.isRunning():
                cancel = getattr(self._chat_worker, "request_cancel", None)
                if callable(cancel):
                    cancel()
                self._chat_worker.wait(1500)
            if self._stt_worker is not None and self._stt_worker.isRunning():
                self._stt_worker.wait(1500)
            if self._tts_worker is not None and self._tts_worker.isRunning():
                self._tts_worker.wait(1500)
            self._media_player.stop()
            self._pcm_player.stop()
            if self._email_chat_worker is not None and self._email_chat_worker.isRunning():
                self._email_chat_worker.request_cancel()
                self._email_chat_worker.wait(1500)
            if self._boot_checks_worker is not None and self._boot_checks_worker.isRunning():
                self._boot_checks_worker.wait(3000)
            if self._hermes_health_worker is not None and self._hermes_health_worker.isRunning():
                # ponytail: gateway 재기동 체크는 최대 60s 걸릴 수 있어 종료를 막음 — 강제 종료
                if not self._hermes_health_worker.wait(3000):
                    self._hermes_health_worker.terminate()
                    self._hermes_health_worker.wait(2000)
            self._metrics_worker.request_stop()
            self._metrics_worker.wait(2000)
            self._api_quota_worker.request_stop()
            self._api_quota_worker.wait(2000)
            self._voice_runtime.shutdown(timeout_sec=2.0)
        except Exception:
            pass
        super().closeEvent(event)
