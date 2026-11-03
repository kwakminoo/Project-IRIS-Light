"""Phase 3 — 설정 UI에서 Hermes 클라이언트 껍질 필드가 코드로 삭제됐는지 자검.

숨김(hide)이 아니라 소스·위젯 트리에 위 문자열이 없어야 한다.
NOTICE/라이선스 MIT 고지 문자열은 이 검사 대상이 아니다.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from iris.config.settings import Settings  # noqa: E402
from iris.infrastructure.agent_runtime import load_pinned_sha  # noqa: E402
from iris.ui.settings.settings_dialog import SettingsDialog  # noqa: E402

_FORBIDDEN_LABELS = (
    "Hermes API URL",
    "Hermes API Key",
    "Hermes 명령",
    "연결 (Ollama / Hermes)",
)

_SETTINGS_DIALOG = (
    Path(__file__).resolve().parents[1] / "ui" / "settings" / "settings_dialog.py"
)


def _string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


def check_settings_source_has_no_shell_labels() -> None:
    literals = _string_literals(_SETTINGS_DIALOG)
    for label in _FORBIDDEN_LABELS:
        assert label not in literals, f"settings_dialog still has label {label!r}"


def check_settings_dialog_has_no_shell_widgets(app: QApplication) -> None:
    dlg = SettingsDialog(Settings(), None)
    try:
        for attr in ("_hermes_url", "_hermes_key", "_hermes_cmd"):
            assert not hasattr(dlg, attr), f"settings dialog still has widget {attr}"
        # 섹션이 늦게 붙으므로 연결 섹션까지 펌프
        for _ in range(40):
            if hasattr(dlg, "_ollama_url"):
                break
            dlg._pump_settings_section()
        assert hasattr(dlg, "_ollama_url"), "Ollama 연결 섹션이 붙지 않음"
        assert hasattr(dlg, "_agent_version"), "에이전트 버전 라벨이 없음"
        pin = load_pinned_sha()
        assert pin and pin in dlg._agent_version.text()
        for child in dlg.findChildren(QLineEdit):
            name = child.objectName() or ""
            tip = child.toolTip() or ""
            ph = child.placeholderText() or ""
            blob = f"{name}\n{tip}\n{ph}\n{child.text()}"
            for label in _FORBIDDEN_LABELS:
                assert label not in blob, f"QLineEdit still exposes {label!r}"
    finally:
        dlg.deleteLater()


if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])
    check_settings_source_has_no_shell_labels()
    check_settings_dialog_has_no_shell_widgets(app)
    print("iris_agent_settings_phase3 ok", load_pinned_sha()[:12])
