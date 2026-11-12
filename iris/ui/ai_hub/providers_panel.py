"""LLM (OpenAI-compatible) providers CRUD — moved out of Settings into AI Hub."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QPainter, QPalette
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.config.settings import Settings
from iris.infrastructure.ollama_client import model_list_tier, roster_summary
from iris.infrastructure.openai_compat_client import ProbeResult, list_model_entries
from iris.storage.api_providers import (
    BASE_URL_PRESETS,
    ApiProvider,
    FreeLlmOffer,
    delete_api_provider,
    get_api_provider,
    load_api_providers,
    mark_provider_status,
    mask_api_key,
    parse_models_text,
    preset_index_for_base_url,
    record_model_probe,
    save_api_providers,
    sync_provider_listing,
    upsert_api_provider,
)
from iris.storage.database import Database
from iris.system.iris_agent_ollama_guard import note_after_provider_direct_ok
from iris.ui.settings.free_llm_list import build_free_llm_list
from iris.ui.settings.hud_dialog import configure_form, make_form_label, make_hint
from iris.ui.shared.theme_tokens import TOKENS
from iris.ui.workers.api_provider_workers import ApiModelsVerifyWorker, ApiProbeWorker


class _StatusDot(QWidget):
    """API 연결 상태 원 — ok=초록, partial=주황, error=빨강, unknown=회색."""

    def __init__(self, status: str = "unknown", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = status if status in ("ok", "partial", "error", "unknown") else "unknown"
        self.setFixedSize(10, 10)

    def set_status(self, status: str) -> None:
        self._status = status if status in ("ok", "partial", "error", "unknown") else "unknown"
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        colors = {
            "ok": QColor("#22c55e"),
            "partial": QColor("#f59e0b"),
            "error": QColor("#ef4444"),
            "unknown": QColor("#94a3b8"),
        }
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colors.get(self._status, colors["unknown"]))
        painter.drawEllipse(1, 1, 8, 8)
        painter.end()


class AiProvidersPanel(QGroupBox):
    """Models / LLM providers form + list (same persist path as old Settings)."""

    def __init__(
        self,
        db: Database | None,
        settings: Settings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Models / LLM (OpenAI 호환)", parent)
        self._db = db
        self._settings = settings
        self._api_providers: list[ApiProvider] = (
            load_api_providers(db) if db is not None else []
        )
        self._api_probe_worker = None
        self._api_models_worker: QThread | None = None
        self._api_row_dots: dict[str, _StatusDot] = {}
        self._verify_after_add_id = ""

        lay = QVBoxLayout(self)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "이름·API Key·Base URL을 채운 뒤 「추가」를 누르세요. Base URL은 "
                "테스트가 실제로 접속해 확정합니다(프리셋은 입력란을 채워줄 뿐입니다). "
                "초록=정상(채팅 모델에 표시), 주황=목록만 성공·대화 실패, 빨강=실패, 회색=미검사."
            )
        )
        lay.addWidget(build_free_llm_list(self._on_free_llm_picked))

        form = QFormLayout()
        configure_form(form)
        self._api_name = QLineEdit()
        self._api_name.setPlaceholderText("예: NVIDIA, OpenAI, OpenRouter")
        self._api_preset = QComboBox()
        for label, url in BASE_URL_PRESETS:
            self._api_preset.addItem(label, url)
        self._style_combo_light_text(self._api_preset)
        self._api_preset.currentIndexChanged.connect(self._on_api_preset_changed)
        self._api_base = QLineEdit()
        self._api_base.setPlaceholderText(
            "예: https://generativelanguage.googleapis.com/v1beta/openai"
        )
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("API Key (로컬 서버면 비워도 됩니다)")
        self._api_models = QLineEdit()
        self._api_models.setPlaceholderText(
            "선택: 모델 id (콤마 구분). 비우면 {base}/models 조회"
        )
        for edit in (self._api_name, self._api_base, self._api_key, self._api_models):
            edit.setMinimumHeight(32)
        self._api_preset.setMinimumHeight(32)
        form.addRow(make_form_label("이름"), self._api_name)
        form.addRow(make_form_label("API Key"), self._api_key)
        form.addRow(make_form_label("제공자 프리셋"), self._api_preset)
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

        lay.addWidget(make_hint("등록된 API"))
        self._api_list_host = QVBoxLayout()
        self._api_list_host.setSpacing(6)
        lay.addLayout(self._api_list_host)
        self._reload_api_provider_rows()

    @staticmethod
    def _open_signup_url(url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    @staticmethod
    def _style_combo_light_text(combo: QComboBox) -> None:
        light = QColor(TOKENS.text_primary)
        pal = combo.palette()
        pal.setColor(QPalette.ColorRole.Text, light)
        pal.setColor(QPalette.ColorRole.ButtonText, light)
        pal.setColor(QPalette.ColorRole.WindowText, light)
        pal.setColor(QPalette.ColorRole.HighlightedText, light)
        combo.setPalette(pal)
        view = combo.view()
        if view is not None:
            vpal = view.palette()
            vpal.setColor(QPalette.ColorRole.Text, light)
            vpal.setColor(QPalette.ColorRole.WindowText, light)
            vpal.setColor(QPalette.ColorRole.HighlightedText, light)
            vpal.setColor(QPalette.ColorRole.Base, QColor(TOKENS.space_navy))
            vpal.setColor(QPalette.ColorRole.Highlight, QColor(37, 99, 235, 115))
            view.setPalette(vpal)

    def persist(self) -> None:
        if self._db is None:
            return
        self._flush_api_form_to_providers(silent=True)
        save_api_providers(self._db, self._api_providers)

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
                tip_parts.append(
                    roster_summary(list(p.models), p.model_states, p.tool_support)
                )
            if p.last_error:
                tip_parts.append(p.last_error[:160])
            key_lbl.setToolTip(" · ".join(tip_parts))
            row.addWidget(key_lbl, 1)

            btn_test = QPushButton("테스트")
            btn_test.setFixedWidth(64)
            btn_test.clicked.connect(lambda _=False, pid=p.id: self._on_api_test(pid))
            btn_verify = QPushButton("모델 정리")
            btn_verify.setFixedWidth(74)
            btn_verify.setToolTip(
                "등록된 모델을 하나씩 호출해 쓸 수 있음·쓸 수 없음·적합하지 않음을 표시합니다. "
                "목록에서 빼지 않습니다."
            )
            btn_verify.clicked.connect(
                lambda _=False, pid=p.id: self._on_api_verify_models(pid)
            )
            btn_del = QPushButton("삭제")
            btn_del.setFixedWidth(52)
            btn_del.clicked.connect(lambda _=False, pid=p.id: self._on_api_delete(pid))
            row.addWidget(btn_test)
            row.addWidget(btn_verify)
            row.addWidget(btn_del)
            self._api_list_host.addWidget(row_w)

    def _on_free_llm_picked(self, offer: FreeLlmOffer) -> None:
        self._api_name.setText(offer.name)
        index = preset_index_for_base_url(offer.base_url)
        self._api_preset.blockSignals(True)
        self._api_preset.setCurrentIndex(index)
        self._api_preset.blockSignals(False)
        url = str(self._api_preset.itemData(index) or offer.base_url)
        if url:
            self._api_base.setText(url)
        self._api_status.setText(
            f"{offer.name} — 이름과 프리셋을 넣었습니다. 키를 붙여 넣으세요."
        )
        self._open_signup_url(offer.signup_url)

    def _on_api_preset_changed(self, index: int) -> None:
        url = str(self._api_preset.itemData(index) or "")
        if url:
            self._api_base.setText(url)
        if not self._api_name.text().strip() and index > 0:
            self._api_name.setText(self._api_preset.itemText(index))

    def _flush_api_form_to_providers(self, *, silent: bool = False) -> ApiProvider | None:
        if self._db is None or not hasattr(self, "_api_name"):
            return None
        name = self._api_name.text().strip()
        key = self._api_key.text().strip()
        base = self._api_base.text().strip().rstrip("/")
        if not name or not base:
            if not silent and not base:
                QMessageBox.warning(
                    self,
                    "API 추가",
                    "Base URL을 입력하세요. 프리셋에서 고르거나 직접 입력할 수 있습니다.",
                )
            return None
        models = parse_models_text(self._api_models.text())
        for existing in self._api_providers:
            if existing.name == name and existing.base_url.rstrip("/") == base:
                if key:
                    existing.api_key = key
                if models:
                    existing.models = models
                upsert_api_provider(self._db, existing)
                self._api_providers = load_api_providers(self._db)
                self._clear_api_form()
                self._reload_api_provider_rows()
                return existing
        provider = ApiProvider(
            name=name,
            base_url=base,
            api_key=key,
            models=models,
            status="unknown",
        )
        upsert_api_provider(self._db, provider)
        self._api_providers = load_api_providers(self._db)
        self._clear_api_form()
        self._reload_api_provider_rows()
        return provider

    def _clear_api_form(self) -> None:
        self._api_name.clear()
        self._api_base.clear()
        self._api_key.clear()
        self._api_models.clear()
        self._api_preset.setCurrentIndex(0)

    def _on_api_add(self) -> None:
        if self._db is None:
            return
        if not self._api_name.text().strip():
            QMessageBox.warning(self, "API 추가", "이름을 입력하세요.")
            return
        provider = self._flush_api_form_to_providers(silent=False)
        if provider is None:
            return
        self._api_status.setText(f"추가됨: {provider.name} — 연결 테스트 중…")
        self._verify_after_add_id = provider.id
        self._on_api_test(provider.id)
        worker = self._api_probe_worker
        if worker is None or not worker.isRunning():
            self._verify_after_add_id = ""

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
        worker = ApiProbeWorker(provider, parent=self)
        self._api_probe_worker = worker
        worker.finished_probe.connect(self._on_api_probe_done)
        worker.start()

    def _on_api_verify_models(self, provider_id: str) -> None:
        if self._db is None:
            return
        provider = next((p for p in self._api_providers if p.id == provider_id), None)
        if provider is None or not provider.models:
            self._api_status.setText(
                "정리할 모델이 없습니다. 먼저 「테스트」로 목록을 받으세요."
            )
            return
        worker = getattr(self, "_api_models_worker", None)
        if worker is not None and worker.isRunning():
            self._api_status.setText("다른 모델 정리가 진행 중입니다…")
            return
        self._api_status.setText(f"{provider.name}: 모델 {len(provider.models)}개 확인 중…")
        worker = ApiModelsVerifyWorker(provider, parent=self)
        worker.verified_one.connect(self._on_api_model_verified_one)
        worker.progress.connect(
            lambda done, total, usable: self._api_status.setText(
                f"{provider.name}: 확인 {done}/{total} · 사용 가능 {usable}"
            )
        )
        worker.finished_all.connect(self._on_api_models_verified_all)
        self._api_models_worker = worker
        worker.start()

    def _on_api_model_verified_one(
        self, provider_id: str, model: str, state: str, tool_support: str
    ) -> None:
        if self._db is None:
            return
        record_model_probe(
            self._db, provider_id, model, state=state, tool_support=tool_support
        )

    def _on_api_models_verified_all(self, provider_id: str, usable: int, total: int) -> None:
        self._api_models_worker = None
        if self._db is None:
            return
        self._api_providers = load_api_providers(self._db)
        self._reload_api_provider_rows()
        name = next(
            (p.name for p in self._api_providers if p.id == provider_id), provider_id
        )
        provider = next((p for p in self._api_providers if p.id == provider_id), None)
        if provider is None:
            self._api_status.setText(f"{name}: 정리 완료 — 전체 {total}")
            return
        counts = [0, 0, 0]
        for model in provider.models:
            rank, _label = model_list_tier(
                model,
                state=provider.model_states.get(model, ""),
                tool=provider.tool_support.get(model, ""),
            )
            counts[rank] += 1
        self._api_status.setText(
            f"{name}: 쓸 수 있음 {counts[0]} · 쓸 수 없음 {counts[1]} · "
            f"적합하지 않음 {counts[2]} / 전체 {len(provider.models)}"
        )

    def _on_api_probe_done(self, provider_id: str, result: object) -> None:
        self._api_probe_worker = None
        if self._db is None:
            return
        if not isinstance(result, ProbeResult):
            return
        status = result.status
        detail = result.detail
        p = next((x for x in self._api_providers if x.id == provider_id), None)
        merged = list(result.models)
        for m in list(p.models) if p else []:
            if m not in merged:
                merged.append(m)
        if status == "ok" and not merged:
            status = "error"
            detail = f"{detail} · 사용 가능한 모델이 없습니다. 모델 목록을 입력하세요."
        mark_provider_status(
            self._db,
            provider_id,
            status=status,
            error="" if status == "ok" else detail,
            models=merged if merged else None,
            resolved_base_url=result.base_url,
            auth_style=result.auth_style,
        )
        if status in ("ok", "partial"):
            self._sync_roster_after_probe(provider_id, result)
        self._api_providers = load_api_providers(self._db)
        self._reload_api_provider_rows()
        label = {"ok": "정상", "partial": "부분 성공", "error": "실패"}.get(status, status)
        verify_after_add = getattr(self, "_verify_after_add_id", "")
        self._verify_after_add_id = ""
        if status == "ok":
            head = f"제공자 직접 연결 정상: {detail[:160]}"
            pnow = next((x for x in self._api_providers if x.id == provider_id), None)
            extra = ""
            if pnow is not None:
                extra = note_after_provider_direct_ok(
                    pnow,
                    db=self._db,
                    hermes_enabled=bool(self._settings.agent_enabled),
                    hermes_base_url=self._settings.agent_base_url,
                )
            self._api_status.setText(head if not extra else f"{head}\n{extra}")
        else:
            self._api_status.setText(f"{label}: {detail[:200]}")
        if verify_after_add == provider_id and status in ("ok", "partial"):
            self._on_api_verify_models(provider_id)

    def _sync_roster_after_probe(self, provider_id: str, result: ProbeResult) -> None:
        """Apply brand listing evidence after probe. No listing → no confirm_missing retire."""
        if self._db is None:
            return
        p = get_api_provider(self._db, provider_id)
        if p is None:
            return
        entries = list(result.model_entries or [])
        root = (result.base_url or p.resolved_base_url or p.base_url or "").strip()
        style = (result.auth_style or p.auth_style or "bearer").strip() or "bearer"
        if not entries and result.models and root and (p.api_key or "").strip():
            try:
                entries = list_model_entries(
                    root, p.api_key, auth_style=style, timeout=20.0
                )
            except Exception:
                entries = []
        if not entries:
            return

        def _refetch():
            return list_model_entries(root, p.api_key, auth_style=style, timeout=20.0)

        sync_provider_listing(
            p,
            entries,
            confirm_missing=True,
            refetch_entries=_refetch if root and (p.api_key or "").strip() else None,
        )
        upsert_api_provider(self._db, p)
