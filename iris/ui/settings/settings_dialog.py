"""Iris Light 설정 — Ollama / Hermes / 이메일 / IDE."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QTimer, QUrl
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from iris.audio.recorder import AudioRecorder
from iris.audio.voice_runtime_client import VoiceRuntimeClient, VoiceRuntimeError
from iris.audio.voice_runtime_manager import VoiceRuntimeProcessManager
from iris.audio.workers import TTSSynthesisWorker, VoiceAnalyzeWorker
from iris.config.settings import Settings
from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.database import Database
from iris.storage.email_accounts import (
    add_email_account,
    load_email_accounts,
    remove_email_account,
)
from iris.storage.voice_prefs import (
    VoicePreferences,
    default_voice_data_dir,
    load_voice_preferences,
    save_voice_preferences,
)
from iris.storage.learning_prefs import (
    LearningPreferences,
    load_learning_preferences,
    save_learning_preferences,
)
from iris.storage.api_providers import (
    ApiProvider,
    delete_api_provider,
    guess_base_url,
    load_api_providers,
    mask_api_key,
    parse_models_text,
    save_api_providers,
    upsert_api_provider,
)
from iris.learning.permission import level_choices, policy_for, request_elevation_hint
from iris.learning.aloha_runtime import bootstrap_runtime, runtime_status
from iris.learning.hook_probe import probe_input_hooks
from iris.storage.user_profile import UserProfile, load_user_profile, save_user_profile
from iris.system.ide_launcher import get_ide_spec, ide_catalog, is_ide_installed
from iris.ui.workers.email_workers import EmailVerifyWorker
from iris.ui.widgets.ide_icons import ide_icon_for, show_ide_not_installed_dialog
from iris.ui.widgets.mic_input_meter import MicThresholdBar
from iris.ui.settings import settings_service
from iris.ui.settings.hud_dialog import (
    configure_form,
    configure_hud_dialog,
    make_form_label,
    make_hint,
    make_scroll_body,
    make_title,
)
from iris.ui.shared.theme_tokens import TOKENS


class _StatusDot(QWidget):
    """API 연결 상태 원 — ok=초록, error=빨강, unknown=회색."""

    def __init__(self, status: str = "unknown", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = status if status in ("ok", "error", "unknown") else "unknown"
        self.setFixedSize(10, 10)

    def set_status(self, status: str) -> None:
        self._status = status if status in ("ok", "error", "unknown") else "unknown"
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        colors = {
            "ok": QColor("#22c55e"),
            "error": QColor("#ef4444"),
            "unknown": QColor("#94a3b8"),
        }
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colors.get(self._status, colors["unknown"]))
        painter.drawEllipse(1, 1, 8, 8)
        painter.end()


@dataclass(frozen=True)
class LightSettingsSelection:
    ollama_base_url: str
    ollama_model: str
    hermes_enabled: bool
    hermes_command: str
    hermes_base_url: str
    hermes_api_key: str
    voice_prefs: VoicePreferences
    learning_prefs: LearningPreferences


class SettingsDialog(QDialog):
    """연결 설정 + 이메일 계정 + IDE Companion."""

    def __init__(self, settings: Settings, db: Database | None = None, parent=None) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self,
            title="Iris Light 설정",
            min_w=760,
            min_h=680,
            default_w=880,
            default_h=820,
        )
        self._settings = settings
        self._db = db
        self._wiki = IrisWiki()
        self._result: LightSettingsSelection | None = None
        self._accounts = load_email_accounts(db) if db is not None else []
        self._voice_prefs = load_voice_preferences(db) if db is not None else VoicePreferences()
        self._learning_prefs = (
            load_learning_preferences(db) if db is not None else LearningPreferences()
        )
        self._iris_root = Path(__file__).resolve().parents[3]
        self._voice_runtime = VoiceRuntimeProcessManager(
            base_url=self._voice_prefs.voice_runtime_url,
            iris_root=self._iris_root,
        )
        self._voice_recommendations: list[dict] = []
        self._analyze_worker: VoiceAnalyzeWorker | None = None
        self._settings_tts_worker: TTSSynthesisWorker | None = None
        self._preview_player = QSoundEffect(self)
        self._mic_monitor = AudioRecorder(self)
        self._mic_monitor.level_changed.connect(self._on_mic_monitor_level)
        self._mic_monitor.failed.connect(self._on_mic_monitor_failed)
        self._verify_worker: EmailVerifyWorker | None = None
        self._api_providers: list[ApiProvider] = (
            load_api_providers(db) if db is not None else []
        )
        self._api_probe_worker = None
        self._api_row_dots: dict[str, _StatusDot] = {}
        profile = load_user_profile(db) if db is not None else UserProfile()
        self._preferred_ide = (profile.preferred_ide or "cursor").strip().lower() or "cursor"
        self._ide_exe_path = profile.ide_exe_path or ""
        self._ide_cli_path = profile.ide_cli_path or ""
        self._project_root = profile.project_root or ""
        self._project_parents = list(profile.project_parents or [])
        self._parents_customized = bool(self._project_parents)
        self._profile_base = profile

        root = QVBoxLayout(self)
        root.setContentsMargins(TOKENS.spacing_xl, TOKENS.spacing_lg, TOKENS.spacing_xl, TOKENS.spacing_lg)
        root.setSpacing(TOKENS.spacing_md)
        root.addWidget(make_title("SETTINGS"))
        root.addWidget(
            make_hint(
                "Ollama · Hermes · API · 음성 · 이메일 · IDE Companion을 설정합니다. "
                "창을 늘리거나 스크롤하면 모든 항목을 가리지 않고 볼 수 있습니다."
            )
        )

        scroll, content_lay = make_scroll_body()

        conn_box = QGroupBox("연결 (Ollama / Hermes)")
        conn_lay = QVBoxLayout(conn_box)
        conn_lay.setSpacing(TOKENS.spacing_sm)
        conn_lay.addWidget(
            make_hint(
                "Hermes 사용 시 채팅은 Hermes API로 전달되며, 선택한 모델이 Hermes에도 동기화됩니다."
            )
        )
        form = QFormLayout()
        configure_form(form)
        self._ollama_url = QLineEdit(settings.ollama_base_url)
        self._ollama_model = QLineEdit(settings.ollama_model)
        self._hermes_cmd = QLineEdit(settings.hermes_command)
        self._hermes_url = QLineEdit(settings.hermes_base_url)
        self._hermes_key = QLineEdit(settings.hermes_api_key)
        self._hermes_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._hermes_on = QCheckBox("Hermes Agent 사용 (채팅을 Hermes API로 전달)")
        self._hermes_on.setChecked(settings.hermes_enabled)
        for edit in (
            self._ollama_url,
            self._ollama_model,
            self._hermes_url,
            self._hermes_key,
            self._hermes_cmd,
        ):
            edit.setMinimumHeight(32)
        form.addRow(make_form_label("Ollama Base URL"), self._ollama_url)
        form.addRow(make_form_label("Ollama Model"), self._ollama_model)
        form.addRow(make_form_label("Hermes API URL"), self._hermes_url)
        form.addRow(make_form_label("Hermes API Key"), self._hermes_key)
        form.addRow(make_form_label("Hermes 명령"), self._hermes_cmd)
        form.addRow(make_form_label(""), self._hermes_on)
        conn_lay.addLayout(form)
        content_lay.addWidget(conn_box)

        if db is not None:
            content_lay.addWidget(self._build_api_providers_box())
            content_lay.addWidget(self._build_voice_box())
            content_lay.addWidget(self._build_permission_box())
            content_lay.addWidget(self._build_learning_runtime_box())
            content_lay.addWidget(self._build_email_box())
            content_lay.addWidget(self._build_ide_box())
            content_lay.addWidget(self._build_project_parents_box())
            content_lay.addWidget(self._build_hermes_control_box())

        content_lay.addStretch(1)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if db is not None:
            self._sync_ide_selection_ui()
            self._reload_account_list()

    def _build_api_providers_box(self) -> QGroupBox:
        box = QGroupBox("API (OpenAI 호환)")
        lay = QVBoxLayout(box)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "이름·API Key·Base URL을 채운 뒤 「추가」를 누르세요. "
                "추가된 API는 아래에 ●이름·키(마스킹)로 표시됩니다. "
                "초록=연결 정상(채팅 모델에 표시), 빨강=실패, 회색=미검사."
            )
        )

        form = QFormLayout()
        configure_form(form)
        self._api_name = QLineEdit()
        self._api_name.setPlaceholderText("예: NVIDIA, OpenAI, OpenRouter")
        self._api_base = QLineEdit()
        self._api_base.setPlaceholderText("비우면 이름으로 추정 (NVIDIA→integrate.api.nvidia.com/v1)")
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("API Key")
        self._api_models = QLineEdit()
        self._api_models.setPlaceholderText("선택: 모델 id (콤마 구분). 비우면 /v1/models 조회")
        for edit in (self._api_name, self._api_base, self._api_key, self._api_models):
            edit.setMinimumHeight(32)
        form.addRow(make_form_label("이름"), self._api_name)
        form.addRow(make_form_label("API Key"), self._api_key)
        form.addRow(make_form_label("Base URL"), self._api_base)
        form.addRow(make_form_label("모델 목록"), self._api_models)
        lay.addLayout(form)

        row = QHBoxLayout()
        btn_add = QPushButton("추가")
        btn_add.clicked.connect(self._on_api_add)
        row.addWidget(btn_add)
        row.addStretch(1)
        lay.addLayout(row)

        self._api_status = QLabel("")
        self._api_status.setWordWrap(True)
        self._api_status.setObjectName("HudHint")
        lay.addWidget(self._api_status)

        # 추가된 API 목록 — 폼 아래
        lay.addWidget(make_hint("등록된 API"))
        self._api_list_host = QVBoxLayout()
        self._api_list_host.setSpacing(6)
        lay.addLayout(self._api_list_host)
        self._reload_api_provider_rows()
        return box

    def _reload_api_provider_rows(self) -> None:
        while self._api_list_host.count():
            item = self._api_list_host.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._api_row_dots.clear()
        if not self._api_providers:
            empty = QLabel("등록된 API 없음 — 위에서 추가하세요")
            empty.setObjectName("HudHint")
            self._api_list_host.addWidget(empty)
            return
        for p in self._api_providers:
            row_w = QWidget()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 4, 0, 4)
            row.setSpacing(10)
            dot = _StatusDot(p.status)
            self._api_row_dots[p.id] = dot
            row.addWidget(dot, 0)

            name_lbl = QLabel(p.name or "(이름 없음)")
            name_lbl.setObjectName("HudMetricName")
            name_lbl.setMinimumWidth(72)
            row.addWidget(name_lbl, 0)

            key_lbl = QLabel(mask_api_key(p.api_key))
            key_lbl.setObjectName("HudHint")
            key_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            tip_parts = [p.base_url or "(base url 없음)", p.status]
            if p.models:
                tip_parts.append("models: " + ", ".join(p.models[:8]))
            if p.last_error:
                tip_parts.append(p.last_error[:160])
            key_lbl.setToolTip(" · ".join(tip_parts))
            row.addWidget(key_lbl, 1)

            btn_test = QPushButton("테스트")
            btn_test.setFixedWidth(64)
            btn_test.clicked.connect(lambda _=False, pid=p.id: self._on_api_test(pid))
            btn_del = QPushButton("삭제")
            btn_del.setFixedWidth(52)
            btn_del.clicked.connect(lambda _=False, pid=p.id: self._on_api_delete(pid))
            row.addWidget(btn_test)
            row.addWidget(btn_del)
            self._api_list_host.addWidget(row_w)

    def _persist_api_providers(self) -> None:
        if self._db is None:
            return
        # 폼에 남은 입력도 저장 전에 반영
        self._flush_api_form_to_providers(silent=True)
        save_api_providers(self._db, self._api_providers)

    def _flush_api_form_to_providers(self, *, silent: bool = False) -> ApiProvider | None:
        """이름+키가 채워져 있으면 목록에 추가(저장 버튼만 누른 경우 대비)."""
        if self._db is None or not hasattr(self, "_api_name"):
            return None
        name = self._api_name.text().strip()
        key = self._api_key.text().strip()
        if not name or not key:
            return None
        base = guess_base_url(name, self._api_base.text())
        if not base:
            if not silent:
                QMessageBox.warning(
                    self,
                    "API 추가",
                    "Base URL이 필요합니다. NVIDIA/OpenAI 등이면 이름을 맞추거나 URL을 입력하세요.",
                )
            return None
        models = parse_models_text(self._api_models.text())
        # 같은 이름+url이면 키만 갱신
        for existing in self._api_providers:
            if existing.name == name and existing.base_url.rstrip("/") == base.rstrip("/"):
                existing.api_key = key
                if models:
                    existing.models = models
                upsert_api_provider(self._db, existing)
                self._api_providers = load_api_providers(self._db)
                self._api_name.clear()
                self._api_base.clear()
                self._api_key.clear()
                self._api_models.clear()
                self._reload_api_provider_rows()
                return existing
        provider = ApiProvider(
            name=name,
            base_url=base.rstrip("/"),
            api_key=key,
            models=models,
            status="unknown",
        )
        upsert_api_provider(self._db, provider)
        self._api_providers = load_api_providers(self._db)
        self._api_name.clear()
        self._api_base.clear()
        self._api_key.clear()
        self._api_models.clear()
        self._reload_api_provider_rows()
        return provider

    def _on_api_add(self) -> None:
        if self._db is None:
            return
        name = self._api_name.text().strip()
        key = self._api_key.text().strip()
        if not name:
            QMessageBox.warning(self, "API 추가", "이름을 입력하세요.")
            return
        if not key:
            QMessageBox.warning(self, "API 추가", "API Key를 입력하세요.")
            return
        base = guess_base_url(name, self._api_base.text())
        if not base:
            QMessageBox.warning(
                self,
                "API 추가",
                "Base URL을 입력하세요.\n예: https://integrate.api.nvidia.com/v1",
            )
            return
        # 폼에 추정 URL 반영
        if not self._api_base.text().strip():
            self._api_base.setText(base)
        provider = self._flush_api_form_to_providers(silent=False)
        if provider is None:
            return
        self._api_status.setText(f"추가됨: {provider.name} — 연결 테스트 중…")
        self._on_api_test(provider.id)

    def _on_api_delete(self, provider_id: str) -> None:
        if self._db is None:
            return
        delete_api_provider(self._db, provider_id)
        self._api_providers = load_api_providers(self._db)
        self._reload_api_provider_rows()
        self._api_status.setText("삭제됨")

    def _on_api_test(self, provider_id: str) -> None:
        if self._db is None:
            return
        provider = next((p for p in self._api_providers if p.id == provider_id), None)
        if provider is None:
            return
        if self._api_probe_worker is not None and self._api_probe_worker.isRunning():
            self._api_status.setText("다른 테스트가 진행 중입니다…")
            return
        self._api_status.setText(f"테스트 중: {provider.name}…")
        from iris.ui.workers.api_provider_workers import ApiProbeWorker

        worker = ApiProbeWorker(provider, parent=self)
        self._api_probe_worker = worker
        worker.finished_probe.connect(self._on_api_probe_done)
        worker.start()

    def _on_api_probe_done(
        self, provider_id: str, ok: bool, detail: str, models: object
    ) -> None:
        self._api_probe_worker = None
        if self._db is None:
            return
        from iris.storage.api_providers import mark_provider_status

        model_list = [str(m) for m in models] if isinstance(models, list) else []
        status = "ok" if ok else "error"
        # ok이지만 모델이 없고 수동 목록도 없으면 피커에 못 올림 → error로
        p = next((x for x in self._api_providers if x.id == provider_id), None)
        manual = list(p.models) if p else []
        merged = list(model_list)
        for m in manual:
            if m not in merged:
                merged.append(m)
        if ok and not merged:
            status = "error"
            detail = (detail or "") + " · 사용 가능한 모델이 없습니다. 모델 목록을 입력하세요."
            ok = False
        mark_provider_status(
            self._db,
            provider_id,
            status=status,
            error="" if ok else detail,
            models=merged if merged else None,
        )
        self._api_providers = load_api_providers(self._db)
        self._reload_api_provider_rows()
        self._api_status.setText(
            f"{'정상' if ok else '실패'}: {detail[:200]}"
        )

    def _build_permission_box(self) -> QGroupBox:
        box = QGroupBox("권한 (업무 학습 · Computer-Use)")
        lay = QVBoxLayout(box)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "학습/자동화가 PC에 접근하는 범위를 설정합니다. "
                "‘제한 없음’은 입력·창·프로세스 조작을 최대한 허용합니다(비밀번호 마스킹은 유지)."
            )
        )
        form = QFormLayout()
        configure_form(form)
        self._perm_level = QComboBox()
        for key, label in level_choices():
            self._perm_level.addItem(label, key)
        self._suppress_unrestricted_prompt = True
        idx = self._perm_level.findData(self._learning_prefs.permission_level)
        self._perm_level.setCurrentIndex(max(0, idx))
        self._perm_desc = QLabel()
        self._perm_desc.setWordWrap(True)
        self._perm_level.currentIndexChanged.connect(self._on_perm_level_changed)
        form.addRow(make_form_label("권한 수준"), self._perm_level)
        lay.addLayout(form)
        lay.addWidget(self._perm_desc)
        self._on_perm_level_changed()
        self._suppress_unrestricted_prompt = False

        tip = QLabel(
            f"관리자: {request_elevation_hint()}\n"
            "보안 소프트웨어가 훅을 막을 수 있습니다. Iris/python 예외 허용을 권장합니다.\n"
            "접근성/앱 제어 정책은 회사 PC에서 IT 확인이 필요할 수 있습니다."
        )
        tip.setWordWrap(True)
        tip.setObjectName("HudHint")
        lay.addWidget(tip)

        row = QHBoxLayout()
        btn_probe = QPushButton("입력 훅 진단")
        btn_probe.clicked.connect(self._on_hook_probe)
        btn_pynput = QPushButton("pynput 설치")
        btn_pynput.clicked.connect(self._install_pynput)
        row.addWidget(btn_probe)
        row.addWidget(btn_pynput)
        row.addStretch(1)
        lay.addLayout(row)
        self._hook_probe_label = QLabel("")
        self._hook_probe_label.setWordWrap(True)
        lay.addWidget(self._hook_probe_label)
        return box

    def _on_perm_level_changed(self) -> None:
        key = str(self._perm_level.currentData() or "normal")
        pol = policy_for(key)
        self._perm_desc.setText(pol.description_ko)
        if key == "unrestricted" and not getattr(self, "_suppress_unrestricted_prompt", False):
            self._prompt_unrestricted_elevation()

    def _prompt_unrestricted_elevation(self) -> None:
        from iris.learning.elevation import is_elevated, relaunch_as_admin

        if is_elevated():
            return
        box = QMessageBox(self)
        box.setWindowTitle("제한 없음 · 관리자 권한")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("제한 없음은 관리자 권한으로 실행해야 합니다.")
        box.setInformativeText(
            "지금 재실행을 누르면 Iris가 종료된 뒤 UAC 확인 후 관리자 권한으로 다시 시작됩니다.\n"
            "취소를 누르면 권한 수준을 이전 값으로 되돌립니다."
        )
        btn_restart = box.addButton("지금 재실행", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_restart)
        box.exec()
        if box.clickedButton() is btn_restart:
            # 저장 후 재실행 — prefs에 unrestricted 반영
            self._learning_prefs.permission_level = "unrestricted"
            if self._db is not None:
                save_learning_preferences(self._db, self._learning_prefs)
            if relaunch_as_admin():
                # 현재 창 닫고 프로세스 종료
                self.accept()
                QApplication = __import__("PyQt6.QtWidgets", fromlist=["QApplication"]).QApplication
                app = QApplication.instance()
                if app is not None:
                    app.quit()
                import sys

                sys.exit(0)
            else:
                QMessageBox.warning(
                    self,
                    "재실행 실패",
                    "관리자 권한 재실행에 실패했습니다. 수동으로 ‘관리자 권한으로 실행’ 해 주세요.",
                )
        else:
            # 취소 → 이전 권한으로
            prev = self._learning_prefs.permission_level
            if prev == "unrestricted":
                prev = "normal"
            self._suppress_unrestricted_prompt = True
            idx = self._perm_level.findData(prev)
            self._perm_level.setCurrentIndex(max(0, idx))
            self._suppress_unrestricted_prompt = False
            self._on_perm_level_changed()

    def _on_hook_probe(self) -> None:
        import sys

        try:
            result = probe_input_hooks()
            lines = [
                f"결과: {'OK' if result.ok else '실패'} · backend={result.backend}",
                *result.messages[:6],
            ]
            try:
                import pynput  # noqa: F401

                lines.append(f"pynput: 설치됨 ({sys.executable})")
            except ImportError:
                lines.append(
                    f"pynput: 없음 — 아래 ‘pynput 설치’로 현재 Iris Python에 설치하세요.\n"
                    f"  {sys.executable} -m pip install pynput"
                )
                lines.append(
                    "Win32 폴백: pynput이 없을 때 Windows 저수준 훅 API로 자동 연결됩니다 "
                    "(별도 외부 프로그램 연결 불필요)."
                )
            if result.backend == "win32":
                lines.append(
                    "현재 진단은 Win32 폴백 가능 상태입니다. "
                    "학습 시작 시 pynput이 없으면 자동으로 Win32 훅이 사용됩니다."
                )
            if not result.ok:
                lines.append(result.security_hint)
                lines.append(result.accessibility_hint)
            from iris.learning.elevation import is_elevated

            if not is_elevated():
                lines.append(result.elevation_hint)
            self._hook_probe_label.setText("\n".join(lines))
        except Exception as exc:
            self._hook_probe_label.setText(f"진단 오류: {exc}")

    def _install_pynput(self) -> None:
        import subprocess
        import sys

        self._hook_probe_label.setText("pynput 설치 중…")
        try:
            kw = {}
            if sys.platform == "win32":
                kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "pynput>=1.7.7"],
                capture_output=True,
                text=True,
                timeout=120,
                **kw,
            )
            if proc.returncode != 0:
                self._hook_probe_label.setText(
                    f"설치 실패:\n{(proc.stderr or proc.stdout or '')[:400]}"
                )
                return
            self._hook_probe_label.setText(
                f"pynput 설치 완료 ({sys.executable}). 다시 ‘입력 훅 진단’을 누르세요."
            )
        except Exception as exc:
            self._hook_probe_label.setText(f"설치 오류: {exc}")

    def _build_learning_runtime_box(self) -> QGroupBox:
        box = QGroupBox("ShowUI-Aloha Runtime (별도 Python)")
        lay = QVBoxLayout(box)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "Actor 실행은 PySide6가 필요해 IRIS(PyQt6)와 분리된 venv를 사용합니다. "
                "`~/.iris-light/runtimes/aloha`"
            )
        )
        self._aloha_runtime_status = QLabel("")
        self._aloha_runtime_status.setWordWrap(True)
        lay.addWidget(self._aloha_runtime_status)
        row = QHBoxLayout()
        btn_refresh = QPushButton("상태 새로고침")
        btn_install = QPushButton("Runtime 설치/복구")
        btn_refresh.clicked.connect(self._refresh_aloha_runtime_status)
        btn_install.clicked.connect(self._bootstrap_aloha_runtime)
        row.addWidget(btn_refresh)
        row.addWidget(btn_install)
        row.addStretch(1)
        lay.addLayout(row)
        self._refresh_aloha_runtime_status()
        return box

    def _refresh_aloha_runtime_status(self) -> None:
        st = runtime_status()
        self._aloha_runtime_status.setText(
            f"{'준비됨' if st['ok'] else '미설치/불완전'} — {st['python']}\n{st['detail']}"
        )

    def _bootstrap_aloha_runtime(self) -> None:
        self._aloha_runtime_status.setText("설치 중… (수 분 소요될 수 있음)")
        try:
            st = bootstrap_runtime(progress=lambda m: self._aloha_runtime_status.setText(m))
            self._aloha_runtime_status.setText(
                f"완료 — {st['python']}\n{st['detail']}"
            )
            QMessageBox.information(self, "Aloha Runtime", "설치가 완료되었습니다.")
        except Exception as exc:
            self._aloha_runtime_status.setText(f"실패: {exc}")
            QMessageBox.warning(self, "Aloha Runtime", str(exc)[:400])

    def _build_email_box(self) -> QGroupBox:
        email_box = QGroupBox("이메일 계정 (Gmail · Naver 등)")
        email_lay = QVBoxLayout(email_box)
        email_lay.setSpacing(TOKENS.spacing_sm)
        email_lay.addWidget(
            make_hint(
                "IMAP/SMTP로 직접 연결합니다. 일반 로그인 비밀번호 대신 앱 비밀번호를 입력하세요."
            )
        )
        self._account_list = QListWidget()
        self._account_list.setMinimumHeight(100)
        self._account_list.setMaximumHeight(140)
        email_lay.addWidget(self._account_list)

        add_form = QFormLayout()
        configure_form(add_form)
        self._new_label = QLineEdit()
        self._new_label.setPlaceholderText("예: 개인 Gmail")
        self._new_address = QLineEdit()
        self._new_address.setPlaceholderText("예: you@gmail.com")
        self._new_password = QLineEdit()
        self._new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_password.setPlaceholderText("앱/애플리케이션 비밀번호")
        for edit in (self._new_label, self._new_address, self._new_password):
            edit.setMinimumHeight(32)
        add_form.addRow(make_form_label("표시 이름"), self._new_label)
        add_form.addRow(make_form_label("이메일 주소"), self._new_address)
        add_form.addRow(make_form_label("비밀번호"), self._new_password)
        email_lay.addLayout(add_form)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("계정 추가")
        self._add_btn.clicked.connect(self._add_account)
        self._remove_btn = QPushButton("선택 삭제")
        self._remove_btn.clicked.connect(self._remove_selected_account)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch(1)
        email_lay.addLayout(btn_row)
        return email_box

    def _build_voice_box(self) -> QGroupBox:
        box = QGroupBox("음성")
        lay = QVBoxLayout(box)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "STT는 녹음 후 입력창에 전사 결과만 넣고 자동 전송하지 않습니다. "
                "TTS는 기준 음성/대본을 확정한 뒤에만 동작합니다. "
                "실제 모델은 .venv-voice + mock 해제 후 사용합니다."
            )
        )

        form = QFormLayout()
        configure_form(form)
        self._voice_stt_on = QCheckBox("STT 사용")
        self._voice_stt_on.setChecked(self._voice_prefs.stt_enabled)

        self._voice_stt_model = QComboBox()
        for name in ("tiny", "base", "small", "medium", "large-v3"):
            self._voice_stt_model.addItem(name, name)
        idx = self._voice_stt_model.findData(self._voice_prefs.stt_model)
        self._voice_stt_model.setCurrentIndex(idx if idx >= 0 else self._voice_stt_model.findData("small"))

        self._voice_stt_lang = QComboBox()
        self._voice_stt_lang.addItem("한국어 (ko)", "ko")
        self._voice_stt_lang.addItem("자동 (auto)", "auto")
        lang_idx = self._voice_stt_lang.findData(self._voice_prefs.stt_language)
        self._voice_stt_lang.setCurrentIndex(lang_idx if lang_idx >= 0 else 0)

        # 연결된(기본) 마이크 + 사용 가능 목록
        default_label = AudioRecorder.default_input_label()
        self._voice_connected_mic = QLabel(f"연결된(기본) 마이크: {default_label}")
        self._voice_connected_mic.setWordWrap(True)

        self._voice_stt_device = QListWidget()
        self._voice_stt_device.setMinimumHeight(110)
        self._voice_stt_device.setToolTip("사용할 마이크를 선택하세요")
        default_item = QListWidgetItem("기본 장치")
        default_item.setData(Qt.ItemDataRole.UserRole, "")
        self._voice_stt_device.addItem(default_item)
        selected_row = 0
        for i, (device_id, label) in enumerate(AudioRecorder.list_input_devices(), start=1):
            item = QListWidgetItem(label or device_id)
            item.setData(Qt.ItemDataRole.UserRole, device_id)
            self._voice_stt_device.addItem(item)
            if device_id and device_id == self._voice_prefs.stt_device_id:
                selected_row = i
        self._voice_stt_device.setCurrentRow(selected_row)
        self._voice_stt_device.currentRowChanged.connect(self._on_mic_device_changed)

        self._mic_threshold_bar = MicThresholdBar(speech_rms=self._voice_prefs.stt_speech_rms)

        self._voice_runtime_url = QLineEdit(self._voice_prefs.voice_runtime_url)
        self._voice_runtime_mock = QCheckBox("voice runtime mock 모드")
        self._voice_runtime_mock.setChecked(self._voice_prefs.voice_runtime_mock)

        self._voice_tts_on = QCheckBox("TTS 사용")
        self._voice_tts_on.setChecked(self._voice_prefs.tts_enabled)
        self._voice_tts_mode = QComboBox()
        for mode, label in (("off", "off"), ("manual", "manual"), ("auto", "auto")):
            self._voice_tts_mode.addItem(label, mode)
        mode_idx = self._voice_tts_mode.findData(self._voice_prefs.tts_mode)
        self._voice_tts_mode.setCurrentIndex(mode_idx if mode_idx >= 0 else 0)

        self._voice_tts_model = QComboBox()
        self._voice_tts_model.setEditable(True)
        default_tts = self._voice_prefs.tts_model or "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
        self._voice_tts_model.addItem(default_tts, default_tts)
        if self._voice_tts_model.findText(default_tts) < 0:
            self._voice_tts_model.setEditText(default_tts)
        else:
            self._voice_tts_model.setCurrentText(default_tts)

        self._voice_ref_audio = QLineEdit(self._voice_prefs.tts_reference_audio)
        self._voice_ref_text = QTextEdit()
        self._voice_ref_text.setPlaceholderText("기준 대본 (사용자가 최종 확정)")
        self._voice_ref_text.setPlainText(self._voice_prefs.tts_reference_text)
        self._voice_ref_text.setMinimumHeight(72)
        self._voice_ref_text.setMaximumHeight(120)

        pick_row = QHBoxLayout()
        pick_row.addWidget(self._voice_ref_audio, 1)
        pick_btn = QPushButton("파일 선택")
        pick_btn.clicked.connect(self._pick_voice_reference_audio)
        confirm_btn = QPushButton("기준 음성 확정")
        confirm_btn.clicked.connect(self._confirm_voice_reference)
        pick_row.addWidget(pick_btn)
        pick_row.addWidget(confirm_btn)

        folder_row = QHBoxLayout()
        self._voice_data_dir = QLineEdit(
            self._voice_prefs.voice_data_dir or default_voice_data_dir()
        )
        folder_row.addWidget(self._voice_data_dir, 1)
        folder_btn = QPushButton("녹음 폴더 선택")
        folder_btn.clicked.connect(self._pick_voice_data_dir)
        analyze_btn = QPushButton("녹음 폴더 분석")
        analyze_btn.clicked.connect(self._analyze_voice_folder)
        folder_row.addWidget(folder_btn)
        folder_row.addWidget(analyze_btn)

        form.addRow(make_form_label(""), self._voice_stt_on)
        form.addRow(make_form_label("STT 모델"), self._voice_stt_model)
        form.addRow(make_form_label("STT 언어"), self._voice_stt_lang)
        form.addRow(make_form_label("Runtime URL"), self._voice_runtime_url)
        form.addRow(make_form_label(""), self._voice_runtime_mock)
        form.addRow(make_form_label(""), self._voice_tts_on)
        form.addRow(make_form_label("TTS 모드"), self._voice_tts_mode)
        form.addRow(make_form_label("TTS 모델"), self._voice_tts_model)
        form.addRow(make_form_label("녹음 폴더"), folder_row)
        form.addRow(make_form_label("선택된 참고 음성"), pick_row)
        form.addRow(make_form_label("참고 대본"), self._voice_ref_text)
        lay.addLayout(form)

        lay.addWidget(make_hint("마이크"))
        lay.addWidget(self._voice_connected_mic)
        lay.addWidget(make_hint("사용 가능한 마이크"))
        lay.addWidget(self._voice_stt_device)
        lay.addWidget(self._mic_threshold_bar)

        lay.addWidget(make_hint("추천 참고 음성 (top 5)"))
        self._voice_rec_list = QListWidget()
        self._voice_rec_list.setMinimumHeight(120)
        lay.addWidget(self._voice_rec_list)
        rec_btn_row = QHBoxLayout()
        preview_btn = QPushButton("미리듣기")
        preview_btn.clicked.connect(self._preview_selected_recommendation)
        select_btn = QPushButton("선택")
        select_btn.clicked.connect(self._select_recommendation)
        rec_btn_row.addWidget(preview_btn)
        rec_btn_row.addWidget(select_btn)
        rec_btn_row.addStretch(1)
        lay.addLayout(rec_btn_row)

        test_row = QHBoxLayout()
        self._voice_test_text = QLineEdit("안녕하세요. 아이리스 음성 테스트입니다.")
        test_row.addWidget(self._voice_test_text, 1)
        test_btn = QPushButton("테스트 음성 생성")
        test_btn.clicked.connect(self._test_tts_generate)
        stop_btn = QPushButton("재생 중지")
        stop_btn.clicked.connect(self._stop_voice_playback)
        cache_btn = QPushButton("캐시 정리")
        cache_btn.clicked.connect(self._clear_voice_cache)
        test_row.addWidget(test_btn)
        test_row.addWidget(stop_btn)
        test_row.addWidget(cache_btn)
        lay.addLayout(test_row)

        self._voice_status = QLabel("")
        self._voice_status.setWordWrap(True)
        lay.addWidget(self._voice_status)
        self._refresh_voice_recommendations_from_runtime(silent=True)
        QTimer.singleShot(0, self._restart_mic_monitor)
        return box

    def _selected_mic_device_id(self) -> str:
        item = self._voice_stt_device.currentItem()
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _on_mic_device_changed(self, _row: int) -> None:
        self._restart_mic_monitor()

    def _restart_mic_monitor(self) -> None:
        self._mic_monitor.stop_monitor()
        device_id = self._selected_mic_device_id()
        label = "기본 장치"
        item = self._voice_stt_device.currentItem()
        if item is not None:
            label = item.text()
        self._voice_connected_mic.setText(
            f"선택된 마이크: {label}  |  시스템 기본: {AudioRecorder.default_input_label()}"
        )
        self._mic_monitor.start_monitor(device_id=device_id, sample_rate=16000, channels=1)

    def _on_mic_monitor_level(self, level: float) -> None:
        self._mic_threshold_bar.set_level(level)

    def _on_mic_monitor_failed(self, err: str) -> None:
        self._mic_threshold_bar.set_status(f"마이크 모니터 오류: {err}")

    def _stop_mic_monitor(self) -> None:
        self._mic_monitor.stop_monitor()

    def _current_voice_prefs_from_ui(self) -> VoicePreferences:
        stt_model = self._voice_stt_model.currentData()
        stt_lang = self._voice_stt_lang.currentData()
        device_id = self._selected_mic_device_id()
        tts_mode = self._voice_tts_mode.currentData()
        return VoicePreferences(
            stt_enabled=self._voice_stt_on.isChecked(),
            stt_model=str(stt_model or "small"),
            stt_language=str(stt_lang or "ko"),
            stt_device_id=str(device_id or ""),
            stt_speech_rms=self._mic_threshold_bar.speech_rms(),
            tts_enabled=self._voice_tts_on.isChecked(),
            tts_mode=str(tts_mode or "off"),
            tts_model=self._voice_tts_model.currentText().strip() or "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            tts_reference_audio=self._voice_ref_audio.text().strip(),
            tts_reference_text=self._voice_ref_text.toPlainText().strip(),
            tts_voice_prompt_hash=self._voice_prefs.tts_voice_prompt_hash,
            tts_volume=self._voice_prefs.tts_volume,
            voice_runtime_url=self._voice_runtime_url.text().strip() or "http://127.0.0.1:18765",
            voice_runtime_mock=self._voice_runtime_mock.isChecked(),
            voice_data_dir=self._voice_data_dir.text().strip() or default_voice_data_dir(),
            pronunciation_dict_json=self._voice_prefs.pronunciation_dict_json,
        )

    def _ensure_settings_voice_runtime(self) -> bool:
        prefs = self._current_voice_prefs_from_ui()
        self._voice_runtime.set_base_url(prefs.voice_runtime_url)
        try:
            self._voice_runtime.ensure_started(mock_mode=prefs.voice_runtime_mock)
            return True
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Voice runtime",
                f"런타임을 시작할 수 없습니다.\n{exc}\n\n"
                "scripts/setup_voice_runtime.ps1 실행 여부를 확인하세요.\n"
                "메인 앱(채팅/위키 등)은 계속 사용할 수 있습니다.",
            )
            return False

    def _pick_voice_reference_audio(self) -> None:
        start = self._voice_data_dir.text().strip() or default_voice_data_dir()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "기준 음성 선택",
            start,
            "Audio Files (*.wav *.mp3 *.m4a *.flac *.ogg *.aac);;All Files (*.*)",
        )
        if path:
            self._voice_ref_audio.setText(path)
            # 참고 음성이 바뀌면 기존 prompt hash 무효화
            self._voice_prefs.tts_voice_prompt_hash = ""

    def _pick_voice_data_dir(self) -> None:
        start = self._voice_data_dir.text().strip() or default_voice_data_dir()
        path = QFileDialog.getExistingDirectory(self, "성우 녹음 폴더 선택", start)
        if path:
            self._voice_data_dir.setText(path)

    def _analyze_voice_folder(self) -> None:
        root = self._voice_data_dir.text().strip() or default_voice_data_dir()
        if not Path(root).is_dir():
            QMessageBox.warning(self, "녹음 폴더 분석", f"폴더가 없습니다:\n{root}")
            return
        if not self._ensure_settings_voice_runtime():
            return
        if self._analyze_worker is not None and self._analyze_worker.isRunning():
            QMessageBox.information(self, "녹음 폴더 분석", "이미 분석 중입니다.")
            return
        prefs = self._current_voice_prefs_from_ui()
        self._voice_status.setText("녹음 폴더 분석 중…")
        worker = VoiceAnalyzeWorker(
            runtime_url=prefs.voice_runtime_url,
            root=root,
            with_transcript=True,
            stt_model_name=prefs.stt_model,
            language=prefs.stt_language,
            parent=self,
        )
        self._analyze_worker = worker
        worker.finished_ok.connect(self._on_analyze_finished)
        worker.failed.connect(self._on_analyze_failed)
        worker.start()

    def _on_analyze_finished(self, payload: object) -> None:
        self._analyze_worker = None
        data = payload if isinstance(payload, dict) else {}
        recs = data.get("recommendations") or []
        self._voice_recommendations = recs if isinstance(recs, list) else []
        self._populate_recommendation_list(self._voice_recommendations)
        count = int(data.get("count") or 0)
        self._voice_status.setText(
            f"분석 완료: {count}개 — manifest: {data.get('manifest_jsonl', '')}"
        )

    def _on_analyze_failed(self, err: str) -> None:
        self._analyze_worker = None
        self._voice_status.setText(f"분석 실패: {err}")
        QMessageBox.warning(self, "녹음 폴더 분석", err)

    def _populate_recommendation_list(self, items: list[dict]) -> None:
        self._voice_rec_list.clear()
        for item in items[:5]:
            name = str(item.get("file_name") or Path(str(item.get("audio_path") or "")).name)
            dur = float(item.get("duration") or 0.0)
            score = float(item.get("quality_score") or 0.0)
            transcript = str(item.get("transcript") or "").strip()
            preview = transcript[:40] + ("…" if len(transcript) > 40 else "")
            text = f"{name} | {dur:.1f}s | 점수 {score:.1f}"
            if preview:
                text += f" | {preview}"
            row = QListWidgetItem(text)
            row.setData(Qt.ItemDataRole.UserRole, item)
            self._voice_rec_list.addItem(row)

    def _refresh_voice_recommendations_from_runtime(self, *, silent: bool = False) -> None:
        try:
            client = VoiceRuntimeClient(base_url=self._voice_runtime_url.text().strip() or self._voice_prefs.voice_runtime_url)
            items = client.voice_references()
            self._voice_recommendations = items
            self._populate_recommendation_list(items)
        except Exception as exc:  # noqa: BLE001
            if not silent:
                self._voice_status.setText(f"추천 목록 로드 실패: {exc}")

    def _selected_recommendation(self) -> dict | None:
        item = self._voice_rec_list.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _preview_selected_recommendation(self) -> None:
        item = self._selected_recommendation()
        if not item:
            QMessageBox.information(self, "미리듣기", "추천 항목을 선택하세요.")
            return
        path = str(item.get("audio_path") or "")
        if not Path(path).is_file():
            QMessageBox.warning(self, "미리듣기", f"파일이 없습니다:\n{path}")
            return
        self._preview_player.stop()
        self._preview_player.setSource(QUrl.fromLocalFile(path))
        self._preview_player.setVolume(1.0)
        self._preview_player.play()

    def _select_recommendation(self) -> None:
        item = self._selected_recommendation()
        if not item:
            QMessageBox.information(self, "선택", "추천 항목을 선택하세요.")
            return
        path = str(item.get("audio_path") or "")
        transcript = str(item.get("transcript") or "")
        self._voice_ref_audio.setText(path)
        if transcript and not self._voice_ref_text.toPlainText().strip():
            self._voice_ref_text.setPlainText(transcript)
        self._voice_prefs.tts_voice_prompt_hash = ""
        self._voice_status.setText("참고 음성을 선택했습니다. 대본을 확인한 뒤 '기준 음성 확정'을 누르세요.")

    def _confirm_voice_reference(self) -> None:
        prefs = self._current_voice_prefs_from_ui()
        if not self._ensure_settings_voice_runtime():
            return
        try:
            voice_hash = settings_service.confirm_voice_reference(prefs.voice_runtime_url, prefs)
            self._voice_prefs.tts_voice_prompt_hash = voice_hash
            self._voice_prefs.tts_reference_audio = prefs.tts_reference_audio
            self._voice_prefs.tts_reference_text = prefs.tts_reference_text
            if self._db is not None:
                save_voice_preferences(self._db, self._current_voice_prefs_from_ui())
            self._voice_status.setText(f"기준 음성 확정 완료 (hash={voice_hash[:12]}…)")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "기준 음성 확정", str(exc))

    def _test_tts_generate(self) -> None:
        prefs = self._current_voice_prefs_from_ui()
        text = self._voice_test_text.text().strip()
        if not text:
            QMessageBox.information(self, "테스트 음성", "테스트 문장을 입력하세요.")
            return
        if not self._ensure_settings_voice_runtime():
            return
        try:
            voice_hash = settings_service.ensure_voice_hash_for_test(prefs.voice_runtime_url, prefs)
            self._voice_prefs.tts_voice_prompt_hash = voice_hash
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "테스트 음성", str(exc))
            return
        self._voice_status.setText("테스트 음성 생성 중…")
        worker = TTSSynthesisWorker(
            runtime_url=prefs.voice_runtime_url,
            text=text,
            voice_prompt_hash=self._voice_prefs.tts_voice_prompt_hash,
            model_name=prefs.tts_model,
            parent=self,
        )
        self._settings_tts_worker = worker
        worker.finished_ok.connect(self._on_settings_tts_ok)
        worker.failed.connect(self._on_settings_tts_failed)
        worker.start()

    def _on_settings_tts_ok(self, payload: object) -> None:
        self._settings_tts_worker = None
        data = payload if isinstance(payload, dict) else {}
        path = str(data.get("audio_path") or "")
        if not path or not Path(path).is_file():
            self._voice_status.setText("테스트 음성 경로가 비어 있습니다.")
            return
        self._preview_player.stop()
        self._preview_player.setSource(QUrl.fromLocalFile(path))
        self._preview_player.setVolume(1.0)
        self._preview_player.play()
        self._voice_status.setText(f"테스트 재생: {path}")

    def _on_settings_tts_failed(self, err: str) -> None:
        self._settings_tts_worker = None
        self._voice_status.setText(f"테스트 실패: {err}")
        QMessageBox.warning(self, "테스트 음성", err)

    def _stop_voice_playback(self) -> None:
        self._preview_player.stop()
        self._voice_status.setText("재생 중지")

    def _clear_voice_cache(self) -> None:
        if not self._ensure_settings_voice_runtime():
            return
        try:
            client = VoiceRuntimeClient(
                base_url=self._voice_runtime_url.text().strip() or self._voice_prefs.voice_runtime_url
            )
            removed = client.clear_cache()
            self._voice_status.setText(f"캐시 정리: {removed}개 삭제")
        except VoiceRuntimeError as exc:
            QMessageBox.warning(self, "캐시 정리", str(exc))

    def _build_ide_box(self) -> QGroupBox:
        ide_box = QGroupBox("IDE Companion 설정")
        ide_lay = QVBoxLayout(ide_box)
        ide_lay.setSpacing(TOKENS.spacing_sm)
        ide_lay.addWidget(
            make_hint(
                "사용할 IDE를 고르세요. 아이콘·이름을 누르면 선택됩니다. "
                "설치되지 않은 IDE는 안내 창이 뜹니다. "
                "바이브코딩은 Iris 채팅(Hermes→Ollama)으로 진행합니다."
            )
        )
        self._ide_selected = QLabel()
        self._ide_selected.setObjectName("IdeSelectedLabel")
        self._ide_selected.setWordWrap(True)
        ide_lay.addWidget(self._ide_selected)

        self._ide_buttons: dict[str, QToolButton] = {}
        grid = QGridLayout()
        grid.setSpacing(8)
        cols = 4
        idx = 0
        for spec in ide_catalog():
            if spec.id == "custom":
                continue
            btn = QToolButton()
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(40, 40))
            installed = is_ide_installed(spec.id)
            btn.setIcon(ide_icon_for(spec.id))
            status = "" if installed else " (미설치)"
            btn.setText(f"{spec.name}{status}")
            btn.setCheckable(True)
            btn.setMinimumSize(110, 78)
            btn.setToolTip(
                f"{spec.name}" + (" — 설치됨" if installed else " — 설치되지 않음")
            )
            btn.clicked.connect(
                lambda _checked=False, ide_id=spec.id: self._on_ide_picked(ide_id)
            )
            self._ide_buttons[spec.id] = btn
            grid.addWidget(btn, idx // cols, idx % cols)
            idx += 1

        custom_btn = QToolButton()
        custom_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        custom_btn.setIconSize(QSize(40, 40))
        custom_btn.setIcon(ide_icon_for("custom"))
        custom_btn.setText("사용자 지정")
        custom_btn.setCheckable(True)
        custom_btn.setMinimumSize(110, 78)
        custom_btn.setToolTip("실행 파일을 직접 선택")
        custom_btn.clicked.connect(lambda: self._on_ide_picked("custom"))
        self._ide_buttons["custom"] = custom_btn
        grid.addWidget(custom_btn, idx // cols, idx % cols)
        ide_lay.addLayout(grid)
        return ide_box

    def _effective_parents_for_ui(self) -> list[str]:
        if self._project_parents:
            return list(self._project_parents)
        from iris.system.project_ops import default_project_parents

        return [str(p) for p in default_project_parents()]

    def _build_project_parents_box(self) -> QGroupBox:
        box = QGroupBox("프로젝트 검색 부모 폴더")
        lay = QVBoxLayout(box)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "Hermes가 '비슷한 프로젝트 열어'라고 할 때 이 폴더들 아래의 "
                "1depth 하위 폴더만 검색합니다. 비우면(기본값 복원) 내장 후보를 씁니다."
            )
        )
        self._parents_list = QListWidget()
        self._parents_list.setMinimumHeight(110)
        lay.addWidget(self._parents_list)
        for path in self._effective_parents_for_ui():
            self._parents_list.addItem(QListWidgetItem(path))

        btn_row = QHBoxLayout()
        add_btn = QPushButton("폴더 추가")
        add_btn.clicked.connect(self._add_project_parent)
        rem_btn = QPushButton("선택 제거")
        rem_btn.clicked.connect(self._remove_project_parent)
        reset_btn = QPushButton("기본값 복원")
        reset_btn.clicked.connect(self._reset_project_parents)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rem_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        return box

    def _parents_from_list_widget(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for i in range(self._parents_list.count()):
            text = (self._parents_list.item(i).text() or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
        return out

    def _add_project_parent(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "프로젝트 모음 폴더 선택")
        if not path:
            return
        try:
            resolved = str(Path(path).expanduser().resolve())
        except OSError:
            resolved = path
        existing = {p.lower() for p in self._parents_from_list_widget()}
        if resolved.lower() in existing:
            return
        self._parents_list.addItem(QListWidgetItem(resolved))
        self._parents_customized = True
        self._project_parents = self._parents_from_list_widget()

    def _remove_project_parent(self) -> None:
        row = self._parents_list.currentRow()
        if row < 0:
            return
        self._parents_list.takeItem(row)
        self._parents_customized = True
        self._project_parents = self._parents_from_list_widget()

    def _reset_project_parents(self) -> None:
        self._parents_customized = False
        self._project_parents = []
        self._parents_list.clear()
        for path in self._effective_parents_for_ui():
            self._parents_list.addItem(QListWidgetItem(path))

    def _build_hermes_control_box(self) -> QGroupBox:
        box = QGroupBox("Iris ↔ Hermes Control")
        lay = QVBoxLayout(box)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "MCP(iris_get_state / iris_invoke)와 iris-work-start 스킬을 Hermes에 동기화합니다. "
                "도구가 안 보이면 동기화 후 새 채팅을 시작하세요."
            )
        )
        self._sync_status = QLabel(self._load_sync_status_text())
        self._sync_status.setWordWrap(True)
        lay.addWidget(self._sync_status)
        self._sync_btn = QPushButton("지금 MCP/스킬 동기화")
        self._sync_btn.clicked.connect(self._run_hermes_control_sync)
        lay.addWidget(self._sync_btn)
        self._sync_worker = None
        return box

    def _load_sync_status_text(self) -> str:
        return settings_service.load_hermes_sync_status_text()

    def _run_hermes_control_sync(self) -> None:
        from iris.ui.workers.hermes_workers import HermesControlSyncWorker

        if self._sync_worker is not None and self._sync_worker.isRunning():
            return
        base = self._hermes_url.text().strip() or "http://127.0.0.1:8642/v1"
        key = self._hermes_key.text().strip()
        cmd = self._hermes_cmd.text().strip() or "hermes"
        self._sync_btn.setEnabled(False)
        self._sync_status.setText("상태: 동기화 중…")
        worker = HermesControlSyncWorker(
            base, api_key=key, command=cmd, parent=self
        )
        self._sync_worker = worker
        worker.progress.connect(self._sync_status.setText)
        worker.finished_ok.connect(self._on_hermes_control_sync_done)
        worker.start()

    def _on_hermes_control_sync_done(self, ok: bool, summary: str) -> None:
        self._sync_worker = None
        self._sync_btn.setEnabled(True)
        text = summary.strip() or ("동기화 완료" if ok else "동기화 실패")
        self._sync_status.setText(text)
        if ok:
            QMessageBox.information(
                self,
                "Iris Control 동기화",
                "동기화 완료.\nHermes gateway를 재기동했고 MCP 도구가 연결됐습니다.\n"
                "Iris에서 새 채팅을 열어 테스트하세요.",
            )
        else:
            QMessageBox.warning(
                self,
                "Iris Control 동기화",
                "일부 실패:\n" + text[:500],
            )

    def _reload_account_list(self) -> None:
        self._account_list.clear()
        for acc in self._accounts:
            self._account_list.addItem(QListWidgetItem(acc.display_name))

    def _sync_ide_selection_ui(self) -> None:
        ide_id = self._preferred_ide
        for key, btn in self._ide_buttons.items():
            btn.setChecked(key == ide_id)
        spec = get_ide_spec(ide_id)
        name = spec.name if spec else ide_id
        if ide_id == "custom":
            installed = bool(self._ide_exe_path and Path(self._ide_exe_path).is_file())
        else:
            installed = is_ide_installed(ide_id, self._ide_exe_path)
        mark = "설치됨" if installed else "경로 확인 필요"
        self._ide_selected.setText(f"선택: {name} ({mark})")

    def _on_ide_picked(self, ide_id: str) -> None:
        if ide_id == "custom":
            path, _ = QFileDialog.getOpenFileName(
                self,
                "IDE 실행 파일 선택",
                "",
                "Executable (*.exe);;All (*.*)",
            )
            if not path:
                self._sync_ide_selection_ui()
                return
            self._preferred_ide = "custom"
            self._ide_exe_path = path
            self._sync_ide_selection_ui()
            return
        if not is_ide_installed(ide_id, ""):
            show_ide_not_installed_dialog(self, ide_id)
            self._sync_ide_selection_ui()
            return
        self._preferred_ide = ide_id
        self._ide_exe_path = ""
        self._sync_ide_selection_ui()

    def _add_account(self) -> None:
        if self._db is None:
            return
        address = self._new_address.text().strip()
        password = self._new_password.text()
        label = self._new_label.text().strip()
        if not address or "@" not in address:
            QMessageBox.warning(self, "이메일 계정", "올바른 이메일 주소를 입력하세요.")
            return
        if not password:
            QMessageBox.warning(self, "이메일 계정", "앱/애플리케이션 비밀번호를 입력하세요.")
            return
        self._add_btn.setEnabled(False)
        worker = EmailVerifyWorker(address, password, parent=self)
        self._verify_worker = worker
        worker.finished_ok.connect(lambda: self._on_verify_ok(address, password, label))
        worker.failed.connect(self._on_verify_failed)
        worker.start()

    def _on_verify_ok(self, address: str, password: str, label: str) -> None:
        self._add_btn.setEnabled(True)
        self._verify_worker = None
        if self._db is None:
            return
        add_email_account(self._db, address, password, label=label)
        self._accounts = load_email_accounts(self._db)
        self._reload_account_list()
        self._new_address.clear()
        self._new_password.clear()
        self._new_label.clear()
        QMessageBox.information(self, "이메일 계정", f"{address} 연결 확인됨 — 저장 목록에 추가했습니다.")

    def _on_verify_failed(self, err: str) -> None:
        self._add_btn.setEnabled(True)
        self._verify_worker = None
        QMessageBox.warning(
            self,
            "이메일 계정",
            f"연결에 실패했습니다.\n\n{err[:400]}\n\n"
            "IMAP/SMTP 사용·2단계 인증·앱 비밀번호를 확인하세요.",
        )

    def _remove_selected_account(self) -> None:
        if self._db is None:
            return
        row = self._account_list.currentRow()
        if row < 0 or row >= len(self._accounts):
            return
        acc = self._accounts[row]
        remove_email_account(self._db, acc.id)
        self._accounts = load_email_accounts(self._db)
        self._reload_account_list()

    def _save_profile_ide(self) -> bool:
        if self._db is None:
            return True
        try:
            profile = settings_service.build_profile_update(
                self._profile_base,
                preferred_ide=self._preferred_ide,
                ide_exe_path=self._ide_exe_path,
                ide_cli_path=self._ide_cli_path,
                project_root=self._project_root,
                parents_customized=self._parents_customized,
                project_parents=(
                    self._parents_from_list_widget() if self._parents_customized else []
                ),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "설정 저장", str(exc))
            return False
        save_user_profile(self._db, profile)
        self._wiki.sync_email_accounts_index(
            [{"address": a.address, "label": a.label} for a in self._accounts]
        )
        return True

    def _accept(self) -> None:
        if not self._save_profile_ide():
            return
        self._stop_mic_monitor()
        voice_prefs = self._current_voice_prefs_from_ui()
        learning_prefs = self._current_learning_prefs_from_ui()
        if self._db is not None:
            save_voice_preferences(self._db, voice_prefs)
            save_learning_preferences(self._db, learning_prefs)
            self._persist_api_providers()
        self._result = LightSettingsSelection(
            ollama_base_url=self._ollama_url.text().strip() or "http://127.0.0.1:11434/v1",
            ollama_model=self._ollama_model.text().strip(),
            hermes_enabled=self._hermes_on.isChecked(),
            hermes_command=self._hermes_cmd.text().strip() or "hermes",
            hermes_base_url=self._hermes_url.text().strip() or "http://127.0.0.1:8642/v1",
            hermes_api_key=self._hermes_key.text().strip(),
            voice_prefs=voice_prefs,
            learning_prefs=learning_prefs,
        )
        # 저장 후에도 비관리자면 재실행 유도 (다음 부팅 자동 elevation과 동일 정책)
        if learning_prefs.permission_level == "unrestricted":
            from iris.learning.elevation import is_elevated, relaunch_as_admin

            if not is_elevated():
                box = QMessageBox(self)
                box.setWindowTitle("제한 없음 · 관리자 권한")
                box.setIcon(QMessageBox.Icon.Warning)
                box.setText("제한 없음은 관리자 권한으로 실행해야 합니다.")
                box.setInformativeText(
                    "지금 재실행을 누르면 관리자 권한으로 Iris를 다시 시작합니다."
                )
                btn_restart = box.addButton(
                    "지금 재실행", QMessageBox.ButtonRole.AcceptRole
                )
                box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                if box.clickedButton() is btn_restart and relaunch_as_admin():
                    self.accept()
                    from PyQt6.QtWidgets import QApplication
                    import sys

                    app = QApplication.instance()
                    if app is not None:
                        app.quit()
                    sys.exit(0)
        self.accept()

    def _current_learning_prefs_from_ui(self) -> LearningPreferences:
        if not hasattr(self, "_perm_level"):
            return LearningPreferences()
        prefs = LearningPreferences(
            permission_level=str(self._perm_level.currentData() or "normal"),
            vlm_provider=self._learning_prefs.vlm_provider,
            vlm_model=self._learning_prefs.vlm_model,
            api_fallback_provider=self._learning_prefs.api_fallback_provider,
            api_fallback_model=self._learning_prefs.api_fallback_model,
            aloha_runtime_python=self._learning_prefs.aloha_runtime_python,
        )
        return prefs

    def reject(self) -> None:
        self._stop_mic_monitor()
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_mic_monitor()
        super().closeEvent(event)

    def selection(self) -> LightSettingsSelection | None:
        return self._result
