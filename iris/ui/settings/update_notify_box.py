"""설정 — 업데이트 알림 허용. 다른 설정 칸과 같은 QCheckBox."""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QGroupBox, QVBoxLayout

from iris.storage.database import Database
from iris.storage.update_notify_prefs import (
    UpdateNotifyPrefs,
    load_update_notify,
    save_update_notify,
)
from iris.ui.settings.hud_dialog import make_hint
from iris.ui.shared.theme_tokens import TOKENS


class UpdateNotifyBox(QGroupBox):
    def __init__(self, db: Database | None) -> None:
        super().__init__("업데이트")
        prefs = load_update_notify(db)
        lay = QVBoxLayout(self)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "켜 두면 업데이트가 있을 때 Iris를 켤 때와 새 채팅을 열 때 한 번씩 안내합니다. "
                "꺼 두면 안내가 나오지 않습니다."
            )
        )
        self.iris_notify = QCheckBox("아이리스 업데이트 알림 허용")
        self.hermes_notify = QCheckBox("헤르메스 업데이트 알림 허용")
        self.iris_notify.setChecked(prefs.iris)
        self.hermes_notify.setChecked(prefs.hermes)
        lay.addWidget(self.iris_notify)
        lay.addWidget(self.hermes_notify)

    def prefs(self) -> UpdateNotifyPrefs:
        return UpdateNotifyPrefs(
            iris=self.iris_notify.isChecked(),
            hermes=self.hermes_notify.isChecked(),
        )


def save_update_notify_box(db: Database, box: UpdateNotifyBox) -> None:
    save_update_notify(db, box.prefs())
