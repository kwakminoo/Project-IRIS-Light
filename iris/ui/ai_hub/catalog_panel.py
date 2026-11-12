"""AI Hub — catalog browse by Iris fitness (iris_chat vs later)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from iris.storage.ai_catalog import (
    AiCatalogEntry,
    AiModality,
    build_catalog,
    iris_chat_entries,
    later_entries,
)
from iris.storage.database import Database
from iris.ui.settings.hud_dialog import make_hint
from iris.ui.shared.theme_tokens import TOKENS

_MODALITY_KO: dict[AiModality, str] = {
    "chat": "채팅",
    "image": "이미지",
    "audio": "음성",
    "video": "영상",
    "embedding": "임베딩",
    "other": "기타",
}


def _row_text(entry: AiCatalogEntry) -> str:
    bits = [entry.label]
    if entry.limit_note:
        bits.append(entry.limit_note)
    elif entry.model_id and entry.model_id not in entry.label:
        bits.append(entry.model_id)
    return " — ".join(bits)


def _later_row_text(entry: AiCatalogEntry) -> str:
    modality = _MODALITY_KO.get(entry.modality, entry.modality)
    return f"[{modality}] {_row_text(entry)}"


class AiCatalogPanel(QGroupBox):
    """Read-only Iris-fit vs later lists. Refresh via build_catalog(db)."""

    def __init__(
        self,
        db: Database | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("모델 카탈로그", parent)
        self._db = db

        lay = QVBoxLayout(self)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "Iris 채팅용은 연결 상태가 정상이고 도구 호출이 확인된 모델입니다. "
                "도구 지원은 위 「Models / LLM」의 모델 정리로 확인합니다. "
                "이미지·음성·영상·임베딩은 나중용 목록에만 두며 Iris 채팅에는 아직 쓰지 않습니다."
            )
        )

        self._iris_list = QListWidget()
        self._iris_list.setMinimumHeight(72)
        self._iris_list.setMaximumHeight(160)
        lay.addWidget(QLabel("Iris 채팅용"))
        lay.addWidget(self._iris_list)

        self._later_list = QListWidget()
        self._later_list.setMinimumHeight(96)
        self._later_list.setMaximumHeight(200)
        lay.addWidget(QLabel("나중용 (Iris 채팅 미사용)"))
        lay.addWidget(self._later_list)

        self.refresh()

    def refresh(self) -> None:
        entries = build_catalog(self._db)
        self._fill(self._iris_list, iris_chat_entries(entries), empty="아직 없음 — 모델 정리로 도구 지원을 확인하세요.")
        self._fill(
            self._later_list,
            later_entries(entries),
            empty="없음",
            row_text=_later_row_text,
        )

    @staticmethod
    def _fill(
        widget: QListWidget,
        rows: list[AiCatalogEntry],
        *,
        empty: str,
        row_text=_row_text,
    ) -> None:
        widget.clear()
        if not rows:
            item = QListWidgetItem(empty)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            widget.addItem(item)
            return
        for entry in rows:
            widget.addItem(QListWidgetItem(row_text(entry)))
