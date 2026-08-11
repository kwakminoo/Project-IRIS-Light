"""채팅 인라인 이미지(마크다운 → HTML → 라이트박스) 자검."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from iris.core.chat_citations import collect_and_tokenize_citations, iris_message_to_chat_html
from iris.core.markdown_text import (
    IRIS_IMAGE_SCHEME,
    extract_chat_image_srcs,
    iris_image_href,
    markdown_to_chat_html,
    markdown_to_plain,
    parse_iris_image_href,
)
from iris.ui.chat.chat_image_view import ChatImageLoader, attach_image_loader
from iris.ui.chat.chat_panel import ChatPanel


def _assert_markdown_images() -> None:
    md = (
        "헬멧 HUD 예시\n\n"
        "![TILSBERK](https://cdn.example.com/hud.jpg)\n\n"
        "관련: [docs](https://docs.example.com/a)"
    )
    plain = markdown_to_plain(md)
    assert "TILSBERK" in plain
    assert "cdn.example.com" not in plain

    html = markdown_to_chat_html(md)
    assert "<img " in html
    assert "iris-image:" in html
    assert "https://cdn.example.com/hud.jpg" in html
    srcs = extract_chat_image_srcs(html)
    assert srcs == ["https://cdn.example.com/hud.jpg"], srcs

    href = iris_image_href(srcs[0])
    assert href.startswith(IRIS_IMAGE_SCHEME)
    assert parse_iris_image_href(href) == srcs[0]

    tok, sources = collect_and_tokenize_citations(md)
    assert "![TILSBERK](https://cdn.example.com/hud.jpg)" in tok
    assert len(sources) == 1
    assert "docs.example.com" in sources[0][1]

    full = iris_message_to_chat_html(md)
    assert "SOURCES" in full and "iris-image:" in full and "<img " in full
    print("markdown images ok")


def _assert_panel_insert(app: QApplication) -> None:
    panel = ChatPanel()
    panel.show()
    app.processEvents()
    import tempfile
    from pathlib import Path

    path = Path(tempfile.gettempdir()) / "iris_chat_img_check.png"
    img = QImage(16, 16, QImage.Format.Format_RGB32)
    img.fill(0xFF38BDF8)
    assert img.save(str(path), "PNG"), "failed to write test png"
    body = f"로컬 이미지 테스트\n\n![dot]({path.as_posix()})"
    panel.append_message_instant("Iris", body)
    app.processEvents()
    html_doc = panel._log.toHtml()
    assert "iris-image:" in html_doc or "img" in html_doc.lower(), html_doc[:500]
    loader: ChatImageLoader = panel._log._iris_image_loader  # type: ignore[attr-defined]
    # append 시 prefetch가 ensure를 호출함 — 로컬은 동기 캐시
    key = path.as_posix()
    if key not in loader._cache:
        loader.ensure(key)
        app.processEvents()
    assert key in loader._cache, list(loader._cache.keys())
    cached = loader._cache[key]
    assert isinstance(cached, QImage) and not cached.isNull()
    print("panel local image ok")


def main() -> int:
    _assert_markdown_images()
    app = QApplication.instance() or QApplication(sys.argv)
    _assert_panel_insert(app)
    print("chat_images ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
