"""Phase 4c: searchable App Directory UI.

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_app_directory_ui
"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from iris.apps.directory import AppDirectory, AppDirectoryEntry, SOURCE_INSTALLED
from iris.ui.chat.app_directory_dialog import AppDirectoryCard, AppDirectoryDialog
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.composer_plus_menu import ComposerPlusMenu


def main() -> None:
    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as raw:
        root = Path(raw)
        html = root / "weather.html"
        html.write_text("<html><body>weather</body></html>", encoding="utf-8")
        directory = AppDirectory(root / "directory.json")
        directory.install(
            AppDirectoryEntry(
                id="weather",
                title="Weather",
                summary="Local forecast",
                resource_uri=str(html),
                source=SOURCE_INSTALLED,
            )
        )

        dialog = AppDirectoryDialog(directory=directory)
        dialog.show()
        app.processEvents()
        assert dialog.findChild(QLabel, "AppDirectoryRecommendLabel") is None
        cards = dialog.findChildren(AppDirectoryCard)
        assert {card.entry.id for card in cards} == {"demo-ping", "weather"}
        weather_text = " ".join(
            label.text() for label in cards[0].findChildren(QLabel)
        ) + " " + " ".join(label.text() for label in cards[1].findChildren(QLabel))
        assert "Weather" in weather_text and "Local forecast" in weather_text
        assert "installed" in weather_text and str(html) in weather_text

        dialog.search.setText("forecast")
        app.processEvents()
        cards = dialog.findChildren(AppDirectoryCard)
        assert [card.entry.id for card in cards] == ["weather"]

        dialog.search.setText("no such app")
        app.processEvents()
        assert not dialog.findChildren(AppDirectoryCard)
        empty = dialog.findChild(QLabel, "AppDirectoryEmpty")
        assert empty is not None and empty.isVisible()

        dialog.close()
        recommended = AppDirectoryDialog(directory=directory, context="ping 데모")
        recommended.show()
        app.processEvents()
        heading = recommended.findChild(QLabel, "AppDirectoryRecommendLabel")
        assert heading is not None and heading.text() == "추천" and heading.isVisible()
        rec_cards = recommended.findChildren(AppDirectoryCard)
        assert any(card.entry.id == "demo-ping" for card in rec_cards)
        recommended.search.setText("forecast")
        app.processEvents()
        assert recommended.findChild(QLabel, "AppDirectoryRecommendLabel") is not None
        ids_after_search = [card.entry.id for card in recommended.findChildren(AppDirectoryCard)]
        assert "demo-ping" in ids_after_search and "weather" in ids_after_search

        chosen: list[str] = []
        dialog.app_chosen.connect(lambda entry: chosen.append(entry.id))
        dialog.search.setText("weather")
        app.processEvents()
        card = dialog.findChildren(AppDirectoryCard)[0]
        launch = card.findChild(QPushButton, "AppDirectoryLaunch")
        assert launch is not None
        launch.click()
        assert chosen == ["weather"]

        opened: list[tuple[str, str]] = []
        notices: list[str] = []

        class _Panel:
            _app_consent_path = root / "consent.json"

            def _ask_app_consent_hook(self, **kwargs) -> bool:
                return True

            def show_app_host(self, html_path: str, title: str = "앱") -> bool:
                opened.append((html_path, title))
                return True

            def show_attach_notice(self, message: str) -> None:
                notices.append(message)

            def _app_consent_store_path(self):
                return self._app_consent_path

            def _ask_app_consent(self, **kwargs):
                return ChatPanel._ask_app_consent(self, **kwargs)

            def _ensure_app_open_consent(self, entry: object) -> bool:
                return ChatPanel._ensure_app_open_consent(self, entry)

        panel = _Panel()
        weather = directory.get("weather")
        assert weather is not None
        assert ChatPanel._open_directory_app(panel, weather)
        assert opened == [(str(html), "Weather")]
        external = AppDirectoryEntry("remote", "Remote", "", "ui://remote", SOURCE_INSTALLED)
        assert not ChatPanel._open_directory_app(panel, external)
        assert notices

        menu = ComposerPlusMenu()
        opened_menu: list[bool] = []
        menu.open_apps_panel.connect(lambda: opened_menu.append(True))
        apps_row = next(
            button
            for button in menu.findChildren(QPushButton)
            if any(label.text() == "Apps" for label in button.findChildren(QLabel))
        )
        apps_row.click()
        assert opened_menu == [True]

    print("app directory ui ok")


if __name__ == "__main__":
    main()
