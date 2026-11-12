"""App Host consent store + open gate.

Run: .venv\\Scripts\\python.exe -m iris.apps._check_app_consent
"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.apps.consent import (
    AppConsentDecision,
    decide_consent,
    deny,
    grant,
    is_allowed,
)
from iris.apps.directory import (
    SOURCE_BUILTIN,
    SOURCE_INSTALLED,
    AppDirectoryEntry,
    BUILTIN_APPS,
)
from iris.ui.chat.chat_panel import ChatPanel


def main() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is QApplication.instance()

    with TemporaryDirectory() as raw:
        root = Path(raw)
        consent = root / "consent.json"
        html = root / "weather.html"
        html.write_text("<html><body>weather</body></html>", encoding="utf-8")

        builtin = BUILTIN_APPS[0]
        assert builtin.source == SOURCE_BUILTIN
        assert decide_consent(
            builtin.id, source=SOURCE_BUILTIN, path=consent
        ) == AppConsentDecision(app_id=builtin.id, allowed=True)
        assert not is_allowed(builtin.id, path=consent)

        installed = AppDirectoryEntry(
            id="weather",
            title="Weather",
            summary="forecast",
            resource_uri=str(html),
            source=SOURCE_INSTALLED,
        )
        denied = decide_consent(
            installed.id, source=SOURCE_INSTALLED, path=consent
        )
        assert denied == AppConsentDecision(app_id="weather", allowed=False)
        assert not is_allowed("weather", path=consent)

        asked: list[str] = []

        def _allow(**kwargs) -> bool:
            asked.append(str(kwargs.get("app_id") or ""))
            return True

        granted = decide_consent(
            installed.id,
            source=SOURCE_INSTALLED,
            path=consent,
            ask_consent=_allow,
            title=installed.title,
            resource_uri=installed.resource_uri,
        )
        assert granted.allowed
        assert asked == ["weather"]
        assert is_allowed("weather", path=consent)

        asked.clear()
        again = decide_consent(
            installed.id,
            source=SOURCE_INSTALLED,
            path=consent,
            ask_consent=_allow,
        )
        assert again.allowed
        assert asked == []

        other = root / "other-consent.json"
        assert not is_allowed("weather", path=other)
        grant("weather", path=other)
        assert is_allowed("weather", path=other)
        assert is_allowed("weather", path=consent)
        deny("weather", path=other)
        assert not is_allowed("weather", path=other)

        opened: list[tuple[str, str]] = []
        asks: list[str] = []

        class _Panel:
            def __init__(self, consent_path: Path, allow: bool) -> None:
                self._app_consent_path = consent_path
                self._allow = allow

            def _ask_app_consent_hook(self, **kwargs) -> bool:
                asks.append(str(kwargs.get("app_id") or ""))
                return self._allow

            def show_app_host(self, html_path: str, title: str = "앱") -> bool:
                opened.append((html_path, title))
                return True

            def show_attach_notice(self, message: str) -> None:
                return None

            def _app_consent_store_path(self):
                return self._app_consent_path

            def _ask_app_consent(self, **kwargs):
                return ChatPanel._ask_app_consent(self, **kwargs)

            def _ensure_app_open_consent(self, entry: object) -> bool:
                return ChatPanel._ensure_app_open_consent(self, entry)

        deny("weather", path=consent)
        asks.clear()
        panel = _Panel(consent, allow=False)
        assert not ChatPanel._open_directory_app(panel, installed)
        assert opened == []
        assert asks == ["weather"]

        asks.clear()
        panel._allow = True
        assert ChatPanel._open_directory_app(panel, installed)
        assert opened == [(str(html), "Weather")]
        assert is_allowed("weather", path=consent)

        asks.clear()
        opened.clear()
        builtin_html = root / "builtin.html"
        builtin_html.write_text("<html><body>builtin</body></html>", encoding="utf-8")
        builtin_local = AppDirectoryEntry(
            id=builtin.id,
            title=builtin.title,
            summary=builtin.summary,
            resource_uri=str(builtin_html),
            source=SOURCE_BUILTIN,
        )
        assert ChatPanel._open_directory_app(panel, builtin_local)
        assert opened == [(str(builtin_html), builtin.title)]
        assert asks == []

        opened.clear()
        asks.clear()
        cancel_panel = _Panel(root / "cancel.json", allow=False)
        fresh = AppDirectoryEntry(
            id="maps",
            title="Maps",
            summary="",
            resource_uri=str(html),
            source=SOURCE_INSTALLED,
        )
        assert not ChatPanel._open_directory_app(cancel_panel, fresh)
        assert opened == []
        assert asks == ["maps"]
        assert not is_allowed("maps", path=cancel_panel._app_consent_path)

    print("app consent ok")


if __name__ == "__main__":
    main()
