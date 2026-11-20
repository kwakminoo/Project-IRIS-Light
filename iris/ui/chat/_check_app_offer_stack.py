"""P4: multi-offer stack on ChatPanel (cap, list, active id).

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_app_offer_stack
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6.QtWidgets import QApplication

from iris.apps.offer import path_offer
from iris.ui.chat.chat_panel import MAX_CHAT_APP_OFFERS, ChatPanel
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready


def main() -> int:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    _ = app

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        html_a = root / "a.html"
        html_b = root / "b.html"
        html_a.write_text(
            "<!DOCTYPE html><html><body>a</body></html>", encoding="utf-8"
        )
        html_b.write_text(
            "<!DOCTYPE html><html><body>b</body></html>", encoding="utf-8"
        )
        offer_a = path_offer("App A", str(html_a), offer_id="stack-a")
        offer_b = path_offer("App B", str(html_b), offer_id="stack-b")

        panel = ChatPanel()
        panel.resize(480, 640)
        shown: list[str] = []

        def _fake_show(
            html_path: str, title: str = "앱", *, offer_id: str = ""
        ) -> bool:
            shown.append(f"{offer_id}:{Path(html_path).name}")
            _ = title
            return Path(html_path).is_file()

        panel.show_app_host = _fake_show  # type: ignore[method-assign]

        assert panel.present_chat_app_offer(offer_a) is True
        assert panel.present_chat_app_offer(offer_b) is True
        assert "stack-a" in panel._chat_app_offers
        assert "stack-b" in panel._chat_app_offers
        listed = panel.list_chat_app_offers()
        assert len(listed) == 2
        assert [o.offer_id for o in listed] == ["stack-a", "stack-b"]
        assert panel.active_chat_app_offer_id == "stack-b"

        assert panel.reopen_chat_app_offer("stack-a") is True
        assert panel.active_chat_app_offer_id == "stack-a"
        assert panel.reopen_chat_app_offer("stack-b") is True
        assert panel.active_chat_app_offer_id == "stack-b"

        # Cap: fill past MAX; oldest (stack-a) must leave.
        assert MAX_CHAT_APP_OFFERS == 32
        for i in range(MAX_CHAT_APP_OFFERS):
            path = root / f"extra-{i}.html"
            path.write_text(
                f"<!DOCTYPE html><html><body>{i}</body></html>", encoding="utf-8"
            )
            oid = f"extra-{i:02d}"
            assert panel.present_chat_app_offer(
                path_offer(f"E{i}", str(path), offer_id=oid)
            ) is True

        assert "stack-a" not in panel._chat_app_offers
        assert panel.reopen_chat_app_offer("stack-a") is False
        assert len(panel.list_chat_app_offers()) == MAX_CHAT_APP_OFFERS
        # a+b then 32 extras → both a and b evicted (oldest-first).
        assert "stack-b" not in panel._chat_app_offers
        assert panel.reopen_chat_app_offer("stack-b") is False

    print("app offer stack ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
