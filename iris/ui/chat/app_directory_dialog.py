"""Search and launch App Host entries from the local App Directory."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.apps.directory import AppDirectory, AppDirectoryEntry
from iris.apps.recommend import recommend_apps
from iris.ui.settings.hud_dialog import (
    configure_hud_dialog,
    make_hint,
    make_scroll_body,
    make_title,
)


class AppDirectoryCard(QFrame):
    launch_clicked = pyqtSignal(object)

    def __init__(self, entry: AppDirectoryEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("AppDirectoryCard")
        self.setStyleSheet(
            "QFrame#AppDirectoryCard { background: rgba(15, 23, 42, 0.72); "
            "border: 1px solid rgba(56, 189, 248, 0.20); border-radius: 8px; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 10, 10)
        row.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(3)
        title = QLabel(entry.title)
        title.setStyleSheet("color: #e2e8f0; font-size: 13px; font-weight: 600;")
        text.addWidget(title)
        summary = QLabel(entry.summary or "설명 없음")
        summary.setWordWrap(True)
        summary.setStyleSheet("color: #94a3b8; font-size: 11px;")
        text.addWidget(summary)
        origin = f"{entry.source} · {entry.server_name}" if entry.server_name else entry.source
        detail = QLabel(f"{origin} · {entry.resource_uri}")
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail.setStyleSheet("color: #64748b; font-size: 10px;")
        text.addWidget(detail)
        row.addLayout(text, 1)

        launch = QPushButton("실행")
        launch.setObjectName("AppDirectoryLaunch")
        launch.setCursor(Qt.CursorShape.PointingHandCursor)
        launch.clicked.connect(lambda: self.launch_clicked.emit(self.entry))
        row.addWidget(launch, 0, Qt.AlignmentFlag.AlignVCenter)


class AppDirectoryDialog(QDialog):
    app_chosen = pyqtSignal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        directory: AppDirectory | None = None,
        context: str = "",
    ) -> None:
        super().__init__(parent)
        self._directory = directory or AppDirectory()
        self._context = context or ""
        self._recommended = recommend_apps(self._context, self._directory.list())
        configure_hud_dialog(
            self,
            title="Apps",
            min_w=420,
            min_h=420,
            default_w=520,
            default_h=560,
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(make_title("앱 디렉터리"))
        root.addWidget(make_hint("사용할 앱을 검색하고 실행하세요."))

        self.search = QLineEdit()
        self.search.setObjectName("AppDirectorySearch")
        self.search.setPlaceholderText("앱 이름 또는 설명 검색")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._reload)
        root.addWidget(self.search)

        scroll, self._list = make_scroll_body()
        root.addWidget(scroll, 1)
        self._reload()

    def _reload(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        recommended = self._recommended
        pinned_ids = {e.id for e in recommended}
        if recommended:
            heading = QLabel("추천")
            heading.setObjectName("AppDirectoryRecommendLabel")
            heading.setStyleSheet(
                "color: #7dd3fc; font-size: 11px; font-weight: 600; padding: 4px 2px 2px;"
            )
            self._list.addWidget(heading)
            for entry in recommended:
                card = AppDirectoryCard(entry)
                card.setProperty("recommend", True)
                card.launch_clicked.connect(self._choose)
                self._list.addWidget(card)

        entries = [
            e for e in self._directory.search(self.search.text()) if e.id not in pinned_ids
        ]
        if not entries and not recommended:
            empty = QLabel("검색 결과가 없습니다.")
            empty.setObjectName("AppDirectoryEmpty")
            empty.setStyleSheet("color: #94a3b8; padding: 18px;")
            self._list.addWidget(empty)
        else:
            for entry in entries:
                card = AppDirectoryCard(entry)
                card.launch_clicked.connect(self._choose)
                self._list.addWidget(card)
        self._list.addStretch(1)

    def _choose(self, entry: AppDirectoryEntry) -> None:
        self.app_chosen.emit(entry)
        self.accept()
