"""모델 선택 — Composer + 메뉴와 동일 HUD 팝업 + Ollama/NVIDIA 목록 창."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from iris.infrastructure.api_model_meta import (
    card_blurb,
    describe_api_model,
    is_multi_model_brand,
    is_nvidia_provider,
    is_single_brand_provider,
)
from iris.infrastructure.model_descriptions import describe_model
from iris.storage.api_providers import is_api_runtime_model, parse_runtime_model_id
from iris.ui.chat.composer_plus_menu import _MenuRow
from iris.ui.chat.skill_mcp_dialogs import _ItemCard, _card_qss
from iris.ui.settings.hud_dialog import configure_hud_dialog, make_hint, make_scroll_body, make_title
from iris.ui.shared.theme_tokens import TOKENS

# 콤보(chat_panel)와 동일 tier 색
_COLOR_MODEL_DEFAULT = "#38bdf8"
_COLOR_MODEL_NO_TOOLS = "#9ca3af"
_COLOR_MODEL_PRO = "#fca5a5"


@dataclass(frozen=True)
class PickerModel:
    runtime: str
    label: str
    supports_tools: bool = True
    requires_subscription: bool = False
    provider_name: str = ""
    provider_base: str = ""
    is_api: bool = False


def picker_tier_color(m: PickerModel) -> str:
    """유료=빨강, 도구 미지원=회색, 그 외=시안."""
    if m.requires_subscription:
        return _COLOR_MODEL_PRO
    if not m.supports_tools:
        return _COLOR_MODEL_NO_TOOLS
    return _COLOR_MODEL_DEFAULT


def _ollama_blurb(m: PickerModel) -> str:
    desc = describe_model(m.runtime) or "Ollama 모델"
    bits = [desc]
    if m.requires_subscription:
        bits.append("Pro/구독")
    if m.supports_tools:
        bits.append("도구·추론 가능")
    else:
        bits.append("도구 호출 미지원")
    return " · ".join(bits)


def _api_blurb(m: PickerModel) -> str:
    parsed = parse_runtime_model_id(m.runtime)
    model_id = parsed[1] if parsed else m.runtime
    meta = describe_api_model(m.provider_name or "API", model_id, base_url=m.provider_base)
    return card_blurb(meta)


class ModelBrandDialog(QDialog):
    """Ollama / NVIDIA 등 브랜드 하위 모델 카드 목록."""

    model_chosen = pyqtSignal(str)  # runtime

    def __init__(
        self,
        title: str,
        models: list[PickerModel],
        parent: QWidget | None = None,
        *,
        categorize: bool = False,
        hint: str = "",
    ) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self,
            title=title,
            min_w=440,
            min_h=480,
            default_w=520,
            default_h=600,
        )
        self.setStyleSheet(self.styleSheet() + _card_qss() + _section_qss())
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(make_title(title))
        root.addWidget(make_hint(hint or "모델을 고른 뒤 「사용」을 누르세요."))

        scroll, self._list_lay = make_scroll_body()
        root.addWidget(scroll, 1)

        if not models:
            empty = QLabel("표시할 모델이 없습니다.")
            empty.setObjectName("HudDialogHint")
            self._list_lay.addWidget(empty)
        elif categorize:
            groups: dict[str, list[PickerModel]] = defaultdict(list)
            for m in models:
                parsed = parse_runtime_model_id(m.runtime)
                mid = parsed[1] if parsed else m.runtime
                cat = describe_api_model(m.provider_name or title, mid, base_url=m.provider_base).category
                groups[cat].append(m)
            order = (
                "LLM/에이전트",
                "비전/멀티모달",
                "이미지 생성",
                "임베딩/검색",
                "음성/TTS",
                "LLM/기타",
                "특수",
                "LLM",
            )
            keys = [k for k in order if k in groups] + sorted(k for k in groups if k not in order)
            for cat in keys:
                sec = QLabel(cat.upper())
                sec.setObjectName("ModelPickerSection")
                self._list_lay.addWidget(sec)
                for m in sorted(groups[cat], key=lambda x: x.label.lower()):
                    self._add_card(m)
        else:
            for m in models:
                self._add_card(m)
        self._list_lay.addStretch(1)

    def _add_card(self, m: PickerModel) -> None:
        blurb = _api_blurb(m) if m.is_api else _ollama_blurb(m)
        card = _ItemCard(m.label, blurb, title_color=picker_tier_color(m))
        card.use_clicked.connect(lambda _n, rt=m.runtime: self._pick(rt))
        self._list_lay.addWidget(card)

    def _pick(self, runtime: str) -> None:
        self.model_chosen.emit(runtime)
        self.accept()


def _section_qss() -> str:
    t = TOKENS
    return f"""
        QLabel#ModelPickerSection {{
            color: {t.text_muted};
            font-size: 9px;
            font-weight: 600;
            letter-spacing: 0.6px;
            padding: 10px 4px 4px 4px;
            background: transparent;
        }}
    """


class ModelPickerMenu(QFrame):
    """입력창 모델명 클릭용 팝업 — Ollama/NVIDIA › + 단일 모델 행."""

    open_ollama = pyqtSignal()
    open_nvidia = pyqtSignal()
    open_brand = pyqtSignal(str)  # provider display name for multi non-nvidia
    model_chosen = pyqtSignal(str)

    def __init__(
        self,
        *,
        has_ollama: bool,
        nvidia_label: str = "",
        multi_brands: list[tuple[str, str]] | None = None,
        singles: list[PickerModel] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self.setObjectName("ComposerPlusMenu")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(
            """
            QFrame#ComposerPlusMenu {
                background-color: #111827;
                border: 1px solid rgba(56, 189, 248, 0.22);
                border-radius: 10px;
            }
            QLabel#ComposerPlusSection {
                color: #64748b;
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 0.6px;
                padding: 6px 10px 1px 10px;
                background: transparent;
            }
            QFrame#ComposerPlusSep {
                background: rgba(148, 163, 184, 0.14);
                border: none;
                max-height: 1px;
                margin: 3px 8px;
            }
            """
        )
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        main = QWidget()
        main.setFixedWidth(240)
        root = QVBoxLayout(main)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(1)

        sec = QLabel("PROVIDERS")
        sec.setObjectName("ComposerPlusSection")
        root.addWidget(sec)

        if has_ollama:
            row = _MenuRow("OL", "Ollama", "로컬·클라우드", show_arrow=True)
            row.clicked.connect(self._on_ollama)
            root.addWidget(row)

        if nvidia_label:
            row = _MenuRow("NV", nvidia_label, "무료 엔드포인트", show_arrow=True)
            row.clicked.connect(self._on_nvidia)
            root.addWidget(row)

        for brand_id, brand_name in multi_brands or ():
            row = _MenuRow("API", brand_name, "모델 목록", show_arrow=True)
            row.clicked.connect(lambda _=False, bid=brand_id: self._on_brand(bid))
            root.addWidget(row)

        singles = list(singles or [])
        if singles:
            sep = QFrame()
            sep.setObjectName("ComposerPlusSep")
            sep.setFixedHeight(1)
            root.addWidget(sep)
            sec2 = QLabel("MODELS")
            sec2.setObjectName("ComposerPlusSection")
            root.addWidget(sec2)
            for m in singles:
                sub = "도구 가능" if m.supports_tools else "도구 미지원"
                if m.requires_subscription:
                    sub = "Pro · " + sub
                row = _MenuRow(
                    "M",
                    m.label,
                    sub,
                    show_arrow=False,
                    title_color=picker_tier_color(m),
                )
                row.clicked.connect(lambda _=False, rt=m.runtime: self._pick(rt))
                root.addWidget(row)

        if not has_ollama and not nvidia_label and not (multi_brands or []) and not singles:
            empty = _MenuRow("—", "모델 없음", "설정에서 API/Ollama 확인")
            empty.setEnabled(False)
            root.addWidget(empty)

        outer.addWidget(main)

    def _on_ollama(self) -> None:
        self.hide()
        self.open_ollama.emit()

    def _on_nvidia(self) -> None:
        self.hide()
        self.open_nvidia.emit()

    def _on_brand(self, brand_id: str) -> None:
        self.hide()
        self.open_brand.emit(brand_id)

    def _pick(self, runtime: str) -> None:
        self.model_chosen.emit(runtime)
        self.hide()

    def popup_above(self, anchor: QWidget) -> None:
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, 0))
        x = pos.x() + max(0, anchor.width() - self.sizeHint().width())
        y = pos.y() - self.sizeHint().height() - 6
        self.move(x, max(8, y))
        self.show()
        self.raise_()
        self.activateWindow()


def split_picker_groups(models: list[PickerModel]) -> tuple[
    list[PickerModel],
    list[PickerModel],
    dict[str, list[PickerModel]],
    list[PickerModel],
]:
    """(ollama, nvidia, other_multi_by_provider_id, singles)."""
    ollama: list[PickerModel] = []
    nvidia: list[PickerModel] = []
    multi: dict[str, list[PickerModel]] = defaultdict(list)
    singles: list[PickerModel] = []
    # provider_id → models for grouping API
    by_pid: dict[str, list[PickerModel]] = defaultdict(list)
    meta_by_pid: dict[str, tuple[str, str]] = {}

    for m in models:
        if not m.is_api:
            ollama.append(m)
            continue
        parsed = parse_runtime_model_id(m.runtime)
        pid = parsed[0] if parsed else m.provider_name or m.runtime
        by_pid[pid].append(m)
        meta_by_pid[pid] = (m.provider_name, m.provider_base)

    for pid, items in by_pid.items():
        pname, pbase = meta_by_pid[pid]
        if is_nvidia_provider(pname, pbase):
            nvidia.extend(items)
            continue
        if is_multi_model_brand(pname, pbase, len(items)) and not is_single_brand_provider(pname):
            multi[pid] = items
            continue
        # 단일 브랜드/소수 모델 → 메뉴에 바로 노출
        singles.extend(items)

    ollama.sort(key=lambda x: x.label.lower())
    nvidia.sort(key=lambda x: x.label.lower())
    singles.sort(key=lambda x: x.label.lower())
    return ollama, nvidia, dict(multi), singles


if __name__ == "__main__":
    o = PickerModel("gemma4:latest", "gemma4:latest")
    n = PickerModel(
        "api:nv:meta/llama-3.1-8b-instruct",
        "NVIDIA · llama",
        True,
        provider_name="NVIDIA",
        provider_base="https://integrate.api.nvidia.com/v1",
        is_api=True,
    )
    g = PickerModel(
        "api:oa:gpt-4o",
        "OpenAI · gpt-4o",
        True,
        provider_name="OpenAI",
        is_api=True,
    )
    no_tools = PickerModel(
        "api:nv:flux",
        "NVIDIA · flux",
        False,
        provider_name="NVIDIA",
        is_api=True,
    )
    pro = PickerModel("cloud:pro", "pro", True, requires_subscription=True)
    ol, nv, mu, si = split_picker_groups([o, n, g])
    assert len(ol) == 1 and len(nv) == 1 and len(si) == 1
    assert is_api_runtime_model(n.runtime)
    assert picker_tier_color(n) == _COLOR_MODEL_DEFAULT
    assert picker_tier_color(no_tools) == _COLOR_MODEL_NO_TOOLS
    assert picker_tier_color(pro) == _COLOR_MODEL_PRO
    print("model_picker_menu self-check ok")
