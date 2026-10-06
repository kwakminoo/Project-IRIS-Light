"""모델 선택 — Composer + 메뉴와 동일 HUD 팝업 + Ollama/NVIDIA 목록 창."""

from __future__ import annotations

import ipaddress
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

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
    availability: str = ""  # ok | unverified | unavailable | ""


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
    from iris.infrastructure.ollama_client import display_name_from_runtime

    bits = [m.label or display_name_from_runtime(m.runtime), tool_support_label(m.tool_support)]
    if m.tool_support == "unknown":
        bits.append("선택하면 1회 확인함")
    return " · ".join(bits)


def _local_blurb(m: PickerModel) -> str:
    bits = ["이 기기에서 실행"]
    if m.requires_subscription:
        bits.append("Pro/구독")
    if m.supports_tools:
        bits.append("도구·추론 가능")
    else:
        bits.append("도구 호출 미지원")
    return " · ".join(bits)


def is_local_endpoint(url: str) -> bool:
    """루프백·사설망 Base URL이면 이 기기(또는 같은 망)의 모델."""
    host = (urlparse((url or "").strip()).hostname or "").strip("[]").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private)


def is_local_picker_model(m: PickerModel) -> bool:
    """제공자 이름과 무관하게, 이 기기에서 도는 채팅 모델인지."""
    if m.is_api:
        return is_local_endpoint(m.provider_base)
    from iris.infrastructure.ollama_client import OllamaModelInfo, is_embedding_model_name

    name = (m.runtime or "").strip()
    if not name or OllamaModelInfo(name=name).is_cloud or is_embedding_model_name(name):
        return False
    return True


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
            from iris.infrastructure.ollama_client import model_list_tier

            ordered = sorted(
                models,
                key=lambda m: (
                    model_list_tier(
                        m.runtime,
                        state=m.availability,
                        tool=m.tool_support or ("no" if not m.supports_tools else ""),
                    )[0],
                    m.label.lower(),
                ),
            )
            for m in ordered:
                self._add_card(m)
        self._list_lay.addStretch(1)

    def _add_card(self, m: PickerModel) -> None:
        if is_local_picker_model(m):
            blurb = _local_blurb(m)
        elif m.is_api:
            blurb = _api_blurb(m)
        else:
            blurb = _ollama_blurb(m)
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

    open_local = pyqtSignal()
    open_ollama = pyqtSignal()
    open_brand = pyqtSignal(str)  # provider id
    model_chosen = pyqtSignal(str)

    def __init__(
        self,
        *,
        local: list[PickerModel] | None = None,
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

        self._add_local_section(root, list(local or []))

        if has_ollama or brands:
            sec = QLabel("PROVIDERS")
            sec.setObjectName("ComposerPlusSection")
            root.addWidget(sec)

        if has_ollama:
            row = _MenuRow("OL", "Ollama", "클라우드", show_arrow=True)
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

        if not local and not has_ollama and not (brands or []) and not singles:
            empty = _MenuRow("—", "모델 없음", "설정에서 API/Ollama 확인")
            empty.setEnabled(False)
            root.addWidget(empty)

        outer.addWidget(main)

    def _add_local_section(self, root: QVBoxLayout, local: list[PickerModel]) -> None:
        """맨 위. 출처와 상관없이 이 기기 모델만 모은다."""
        if not local:
            return
        sec = QLabel("로컬 모델")
        sec.setObjectName("ComposerPlusSection")
        root.addWidget(sec)
        if len(local) >= BRAND_MIN_MODELS:
            row = _MenuRow("LM", "로컬 모델", f"이 기기 · {len(local)}개", show_arrow=True)
            row.clicked.connect(self._on_local)
            root.addWidget(row)
            return
        for m in local:
            row = _MenuRow(
                "LM",
                m.label,
                "이 기기",
                show_arrow=False,
                title_color=picker_tier_color(m),
            )
            row.clicked.connect(lambda _=False, rt=m.runtime: self._pick(rt))
            root.addWidget(row)

    def _on_local(self) -> None:
        self.hide()
        self.open_local.emit()

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
) -> tuple[list[PickerModel], list[PickerModel], dict[str, list[PickerModel]], list[PickerModel]]:
    """(local, ollama, api_brands_by_provider_id, singles).

    로컬 채팅 모델은 제공자와 상관없이 첫 묶음으로 뺀다. 나머지는 제공자 이름이
    아니라 **실제 모델 수**로만 분기함. 모델이 많은 제공자는 하위 목록 창
    (`ModelBrandDialog`)으로 묶고, 적은 제공자는 팝업에 바로 노출함.
    """
    local: list[PickerModel] = []
    ollama: list[PickerModel] = []
    by_pid: dict[str, list[PickerModel]] = defaultdict(list)
    for m in models:
        if is_local_picker_model(m):
            local.append(m)
            continue
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

    local.sort(key=lambda x: x.label.lower())
    ollama.sort(key=lambda x: x.label.lower())
    singles.sort(key=lambda x: x.label.lower())
    return local, ollama, brands, singles


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
    # gemma4:latest 는 로컬. 클라우드·원격 API는 제공자 쪽에 남음.
    cloud = PickerModel("gemma4:31b-cloud", "gemma4 cloud")
    local_api = PickerModel(
        "api:lm:llama",
        "llama",
        provider_name="NVIDIA",
        provider_base="http://127.0.0.1:1234/v1",
        is_api=True,
    )
    assert is_local_endpoint("http://192.168.0.8:11434/v1")
    assert not is_local_endpoint("https://integrate.api.nvidia.com/v1")
    assert is_local_picker_model(o) and is_local_picker_model(local_api)
    assert not is_local_picker_model(cloud) and not is_local_picker_model(n)
    # 모델 2개인 제공자는 그대로 노출, BRAND_MIN_MODELS 이상이면 브랜드로 묶음
    local, ol, brands, si = split_picker_groups([o, cloud, local_api, n, g])
    assert [m.runtime for m in local] == ["gemma4:latest", "api:lm:llama"]
    assert [m.runtime for m in ol] == ["gemma4:31b-cloud"]
    assert brands == {} and len(si) == 2
    many = [
        PickerModel(
            f"api:gm:models/gemini-{i}",
            f"Gemini · gemini-{i}",
            provider_name="Gemini",
            provider_base="https://generativelanguage.googleapis.com/v1beta",
            is_api=True,
        )
        for i in range(BRAND_MIN_MODELS)
    ]
    local, ol, brands, si = split_picker_groups([o, *many])
    assert [m.runtime for m in local] == ["gemma4:latest"]
    assert list(brands) == ["gm"] and len(brands["gm"]) == BRAND_MIN_MODELS
    assert si == [] and ol == []
    assert brand_label(brands["gm"]) == "Gemini"
    assert is_api_runtime_model(n.runtime)
    assert picker_tier_color(n) == _COLOR_MODEL_DEFAULT
    assert picker_tier_color(no_tools) == _COLOR_MODEL_NO_TOOLS
    assert picker_tier_color(pro) == _COLOR_MODEL_PRO
    print("model_picker_menu self-check ok")
