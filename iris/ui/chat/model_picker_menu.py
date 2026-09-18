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

from iris.infrastructure.api_model_meta import tool_support_label
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
_COLOR_MODEL_UNKNOWN = "#fbbf24"  # 도구지원 미확인 — 선택 시 1회 프로브함

# 이 수 이상 모델을 가진 제공자는 하위 목록 창으로 묶음 (제공자 이름과 무관)
BRAND_MIN_MODELS = 6


@dataclass(frozen=True)
class PickerModel:
    runtime: str
    label: str
    supports_tools: bool = True
    requires_subscription: bool = False
    provider_name: str = ""
    provider_base: str = ""
    is_api: bool = False
    tool_support: str = ""  # 커스텀 API 전용 — yes | no | unknown


def picker_tier_color(m: PickerModel) -> str:
    """유료=빨강, 도구 미지원=회색, 도구 미확인=주황, 그 외=시안."""
    if m.requires_subscription:
        return _COLOR_MODEL_PRO
    if not m.supports_tools:
        return _COLOR_MODEL_NO_TOOLS
    if m.tool_support == "unknown":
        return _COLOR_MODEL_UNKNOWN
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
    bits = [model_id, tool_support_label(m.tool_support)]
    if m.tool_support == "unknown":
        bits.append("선택하면 1회 확인함")
    return " · ".join(bits)


class ModelBrandDialog(QDialog):
    """Ollama / NVIDIA 등 브랜드 하위 모델 카드 목록."""

    model_chosen = pyqtSignal(str)  # runtime

    def __init__(
        self,
        title: str,
        models: list[PickerModel],
        parent: QWidget | None = None,
        *,
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
        else:
            # 도구 확인된 모델을 앞에 — 근거 없는 카테고리 분류는 쓰지 않음
            for m in sorted(models, key=lambda x: (x.tool_support != "yes", x.label.lower())):
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
    """입력창 모델명 클릭용 팝업 — 제공자 › (모델 다수) + 단일 모델 행."""

    open_ollama = pyqtSignal()
    open_brand = pyqtSignal(str)  # provider id
    model_chosen = pyqtSignal(str)

    def __init__(
        self,
        *,
        has_ollama: bool,
        brands: list[tuple[str, str, int]] | None = None,  # (provider_id, 표시명, 모델수)
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

        for brand_id, brand_name, count in brands or ():
            badge = (brand_name[:2] or "AP").upper()
            row = _MenuRow(badge, brand_name, f"모델 {count}개", show_arrow=True)
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

        if not has_ollama and not (brands or []) and not singles:
            empty = _MenuRow("—", "모델 없음", "설정에서 API/Ollama 확인")
            empty.setEnabled(False)
            root.addWidget(empty)

        outer.addWidget(main)

    def _on_ollama(self) -> None:
        self.hide()
        self.open_ollama.emit()

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


def brand_label(items: list[PickerModel], fallback: str = "API") -> str:
    return next((m.provider_name for m in items if m.provider_name), fallback)


def split_picker_groups(
    models: list[PickerModel],
) -> tuple[list[PickerModel], dict[str, list[PickerModel]], list[PickerModel]]:
    """(ollama, api_brands_by_provider_id, singles).

    제공자 이름 철자가 아니라 **실제 모델 수**로만 분기함. 모델이 많은 제공자는
    하위 목록 창(`ModelBrandDialog`)으로 묶고, 적은 제공자는 팝업에 바로 노출함.
    """
    ollama: list[PickerModel] = []
    by_pid: dict[str, list[PickerModel]] = defaultdict(list)
    for m in models:
        if not m.is_api:
            ollama.append(m)
            continue
        parsed = parse_runtime_model_id(m.runtime)
        pid = parsed[0] if parsed else m.provider_name or m.runtime
        by_pid[pid].append(m)

    brands: dict[str, list[PickerModel]] = {}
    singles: list[PickerModel] = []
    for pid, items in by_pid.items():
        if len(items) >= BRAND_MIN_MODELS:
            brands[pid] = sorted(items, key=lambda x: x.label.lower())
        else:
            singles.extend(items)

    ollama.sort(key=lambda x: x.label.lower())
    singles.sort(key=lambda x: x.label.lower())
    return ollama, brands, singles


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
    # 모델 2개인 제공자는 그대로 노출, BRAND_MIN_MODELS 이상이면 브랜드로 묶음
    ol, brands, si = split_picker_groups([o, n, g])
    assert len(ol) == 1 and brands == {} and len(si) == 2
    many = [
        PickerModel(
            f"api:gm:models/gemini-{i}",
            f"Gemini · gemini-{i}",
            provider_name="Gemini",
            is_api=True,
        )
        for i in range(BRAND_MIN_MODELS)
    ]
    ol, brands, si = split_picker_groups([o, *many])
    assert list(brands) == ["gm"] and len(brands["gm"]) == BRAND_MIN_MODELS
    assert si == [] and len(ol) == 1
    assert brand_label(brands["gm"]) == "Gemini"
    assert is_api_runtime_model(n.runtime)
    assert picker_tier_color(n) == _COLOR_MODEL_DEFAULT
    assert picker_tier_color(no_tools) == _COLOR_MODEL_NO_TOOLS
    assert picker_tier_color(pro) == _COLOR_MODEL_PRO
    print("model_picker_menu self-check ok")
