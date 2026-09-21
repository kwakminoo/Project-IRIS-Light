"""Hermes 필수 계약 — 설정 UI·컨트롤 액션으로 끌 수 없음을 확인함.

총괄표 연번 9는 「Hermes 미사용 경로에 tools 배관 부재」인데, 설계상 Hermes를
필수로 두어 그 경로 자체를 없애는 방향으로 종결함. 따라서 Hermes를 끄는 입구가
다시 생기면 연번 9가 되살아남 — 그것을 막는 검사임.
"""

from __future__ import annotations

import dataclasses
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

from iris.config.settings import Settings  # noqa: E402
from iris.system.control_surface import ActionRegistry  # noqa: E402
from iris.ui.control_bindings import _register_actions  # noqa: E402
from iris.ui.settings.settings_dialog import LightSettingsSelection, SettingsDialog  # noqa: E402


def check_default_is_on() -> None:
    assert Settings().hermes_enabled is True, "Hermes 기본값이 꺼져 있음"


def check_settings_dialog_has_no_switch(app: QApplication) -> None:
    fields = {f.name for f in dataclasses.fields(LightSettingsSelection)}
    assert "hermes_enabled" not in fields, "설정 저장 구조체에 hermes_enabled가 남아 있음"

    dlg = SettingsDialog(Settings(), None)
    try:
        assert not hasattr(dlg, "_hermes_on"), "설정 화면에 Hermes 끄기 체크박스가 남아 있음"
        assert dlg.selection() is None
    finally:
        dlg.deleteLater()


def check_control_action_rejects_disable() -> None:
    surface = MagicMock()
    surface.registry = reg = ActionRegistry()
    _register_actions(MagicMock(), surface)

    off = reg.invoke("settings.set", {"hermes_enabled": False})
    assert off["ok"] is False, "settings.set이 Hermes 끄기를 수용함"
    assert "hermes" in (off["error"] or "").lower(), off["error"]

    # 켜는 요청은 무해한 no-op이어야 함 (기존 클라이언트 호환)
    on = reg.invoke("settings.set", {"hermes_enabled": True})
    assert on["ok"] is True, on.get("error")


if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])
    check_default_is_on()
    check_settings_dialog_has_no_switch(app)
    check_control_action_rejects_disable()
    print("hermes required self-check ok")
