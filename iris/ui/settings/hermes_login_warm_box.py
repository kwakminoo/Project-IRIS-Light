"""설정 — 로그인 시 Iris Agent 미리 기동."""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QGroupBox, QVBoxLayout

from iris.storage.database import Database
from iris.storage.hermes_login_warm_prefs import (
    HermesLoginWarmPrefs,
    load_hermes_login_warm,
    save_hermes_login_warm,
)
from iris.ui.settings.hud_dialog import make_hint
from iris.ui.shared.theme_tokens import TOKENS


class HermesLoginWarmBox(QGroupBox):
    def __init__(self, db: Database | None) -> None:
        super().__init__("Iris Agent 미리 기동")
        prefs = load_hermes_login_warm(db)
        lay = QVBoxLayout(self)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "켜 두면 Windows에 로그인할 때 Iris Agent를 백그라운드에서 "
                "미리 켭니다. Iris를 열 때 차가운 기동을 줄입니다."
            )
        )
        self.enabled = QCheckBox("로그인 시 Iris Agent 미리 켜기")
        self.enabled.setChecked(prefs.enabled)
        lay.addWidget(self.enabled)

    def prefs(self) -> HermesLoginWarmPrefs:
        return HermesLoginWarmPrefs(enabled=self.enabled.isChecked())


def save_hermes_login_warm_box(db: Database, box: HermesLoginWarmBox) -> None:
    save_hermes_login_warm(db, box.prefs())
