"""Self-check: Chrome-like UA strips QtWebEngine."""

from __future__ import annotations

from pathlib import Path

from iris.ui.browser.webengine_setup import chrome_like_user_agent


def main() -> int:
    raw = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) QtWebEngine/6.11.1 Chrome/140.0.0.0 Safari/537.36"
    )
    ua = chrome_like_user_agent(raw)
    assert "QtWebEngine" not in ua, ua
    assert "Chrome/140" in ua, ua
    assert chrome_like_user_agent(ua) == ua

    from iris.ui.browser import webengine_setup as setup

    src = Path(setup.__file__).read_text(encoding="utf-8")
    assert "def _page_class" in src
    assert "creating a new class per page crashes" in src
    print("webengine_setup ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
