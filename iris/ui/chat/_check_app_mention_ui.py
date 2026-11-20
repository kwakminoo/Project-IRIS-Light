"""Unit 3: composer @app mention completer + send opens directory app.

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_app_mention_ui
"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from iris.apps.directory import AppDirectory, AppDirectoryEntry, SOURCE_INSTALLED
from iris.ui.chat.chat_panel import ChatPanel


def main() -> None:
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as raw:
        root = Path(raw)
        html = root / "ping.html"
        html.write_text("<html><body>ping</body></html>", encoding="utf-8")
        directory = AppDirectory(root / "directory.json")
        directory.install(
            AppDirectoryEntry(
                id="demo-ping",
                title="데모 앱",
                summary="ping",
                resource_uri=str(html),
                source=SOURCE_INSTALLED,
            )
        )

        panel = ChatPanel()
        panel._app_directory = directory
        panel._app_consent_path = root / "consent.json"
        panel._ask_app_consent_hook = lambda **kwargs: True
        opened: list[tuple[str, str]] = []
        sent: list[tuple[str, list[str]]] = []

        panel.show_app_host = lambda html_path, title="앱": (
            opened.append((html_path, title)) or True
        )
        panel.send_clicked.connect(lambda text, paths: sent.append((text, list(paths))))

        panel._input.setPlainText("@app")
        cursor = panel._input.textCursor()
        cursor.setPosition(len("@app"))
        panel._input.setTextCursor(cursor)
        panel._refresh_app_mention_popup()
        app.processEvents()
        popup = panel._app_mention_popup
        assert popup.isVisible(), "typing @app should show mention popup"
        assert popup.count() >= 1
        entry_ids = [
            popup.item(i).data(Qt.ItemDataRole.UserRole).id
            for i in range(popup.count())
        ]
        assert "demo-ping" in entry_ids

        token = panel.insert_app_mention("demo-ping")
        assert token == "@app:demo-ping "
        assert panel._input.toPlainText() == "@app:demo-ping "
        assert not popup.isVisible()

        panel._input.setPlainText("실행 @app:demo-ping 해줘")
        panel._emit_send()
        app.processEvents()
        assert opened == [(str(html), "데모 앱")], opened
        assert sent and "@app:demo-ping" in sent[0][0], sent

        opened.clear()
        panel._input.setPlainText("그냥 안녕")
        panel._emit_send()
        assert opened == []

    print("app mention ui ok")


if __name__ == "__main__":
    main()
