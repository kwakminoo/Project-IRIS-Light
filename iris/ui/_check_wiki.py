"""ponytail: Iris Wiki write / slug / inbox self-check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.knowledge.iris_wiki import (
    IrisWiki,
    IrisWikiNote,
    markdown_heading,
    match_wiki_notes,
    slugify_note_name,
)
from iris.ui.knowledge.wiki_graph_view import camera_aim, rotate_xyz


def main() -> None:
    assert slugify_note_name("Hello World!") == "hello-world"
    assert "위키" in slugify_note_name("Iris 위키 메모")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        path, rel = wiki.write_inbox_note(
            "Example Site",
            "- about: demo\n- topic: wiki",
            source_url="https://example.com",
        )
        assert rel == "inbox/example-site.md", rel
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert "# Example Site" in text
        assert "https://example.com" in text
        assert any(n.rel_path == "user/inbox/example-site.md" for n in wiki.list_notes())

        try:
            wiki.write_inbox_note("x", "y", rel_path="docs/evil.md")
            raise AssertionError("docs write should fail")
        except ValueError:
            pass

        try:
            wiki.write_inbox_note("x", "y", rel_path="../outside.md")
            raise AssertionError("traversal should fail")
        except ValueError:
            pass

    assert markdown_heading("# network_security.pdf\n\nbody") == "network_security.pdf"
    notes = [
        IrisWikiNote("user/inbox/network_security.md", "Network Security", "user/inbox", "user"),
        IrisWikiNote("user/inbox/web.md", "Web Security Notes", "user/inbox", "user"),
        IrisWikiNote("user/inbox/other.md", "재고 관리", "user/inbox", "user"),
    ]
    sec = match_wiki_notes(notes, "security")
    assert [n.title for n in sec] == ["Network Security", "Web Security Notes"], sec
    assert match_wiki_notes(notes, "재고")[0].title == "재고 관리"
    assert match_wiki_notes(notes, "") == []
    for x, y, z in ((0.4, -0.2, 0.3), (-0.5, 0.1, 0.2), (0.1, 0.6, -0.4)):
        angle, tilt = camera_aim(x, y, z)
        x2, y2, z2 = rotate_xyz(x, y, z, angle, tilt)
        assert abs(x2) < 0.08 and abs(y2) < 0.08 and z2 > 0, (x2, y2, z2)

    from PyQt6.QtWidgets import QApplication

    from iris.ui.workspaces.obsidian_workspace_page import ObsidianWorkspacePage

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        wiki.write_inbox_note(
            "Network Security",
            "notes",
            rel_path="inbox/network-security.md",
        )
        wiki.write_user_note("사용자/취미/기타.md", "# 기타\n\n[[가치관]]")
        wiki.write_user_note("사용자/가치관/삶.md", "# 가치관\n\nkeep")
        page = ObsidianWorkspacePage()
        page.resize(1200, 700)
        page.set_wiki(wiki)
        # 스크롤 시퀀스: 요약 → 캡션 → 상태 → 미리보기 → 버튼 (WikiOriginalPane 없음)
        assert page._note_scroll.widget() is page._note_col
        assert not hasattr(page, "_original_slot") or getattr(page, "_original_slot", None) is None
        note_lay = page._note_col.layout()
        assert note_lay is not None
        assert note_lay.itemAt(0).widget() is page._body
        assert note_lay.itemAt(1).widget() is page._original_cap
        assert note_lay.itemAt(2).widget() is page._original_status
        assert note_lay.itemAt(3).widget() is page._original_preview
        assert note_lay.itemAt(4).widget() is page._original_full_btn
        assert page._original_cap.text() == "원본 문서"
        assert page._original_status.text() == "불러오는 중…"
        assert page._original_full_btn.text() == "전체 보기"
        assert page._original_preview.objectName() == "WikiOriginalPreview"
        from iris.knowledge.wiki_original import first_page_png, require_original
        from iris.ui.workspaces.obsidian_workspace_page import _ORIGINAL_PREVIEW_MIN

        try:
            import pymupdf
        except ImportError:
            pymupdf = None
        if pymupdf is not None:
            pdf = root / "sample.pdf"
            doc = pymupdf.open()
            page_pdf = doc.new_page(width=240, height=320)
            page_pdf.insert_text((40, 80), "wiki preview")
            doc.save(str(pdf))
            doc.close()
            note_path = wiki.user_root / "inbox" / "with-original.md"
            note_path.parent.mkdir(parents=True, exist_ok=True)
            long_summary = "# With Original\n\n" + ("요약 문단.\n\n" * 40)
            note_path.write_text(long_summary, encoding="utf-8")
            asset = require_original(note_path, kind="pdf", source=str(pdf))
            assert asset.endswith("original.pdf"), asset
            png = first_page_png(note_path.parent / asset)
            assert png and png[:4] == b"\x89PNG"
            page.resize(900, 500)
            page.show()
            QApplication.processEvents()
            page.show_note("user/inbox/with-original.md")
            for _ in range(20):
                QApplication.processEvents()
                if not page._original_full_btn.isHidden() and page._original_status.isHidden():
                    break
            assert not page._original_cap.isHidden()
            assert not page._original_full_btn.isHidden()
            assert page._original is None or page._original.isHidden()
            pix = page._original_preview.pixmap()
            assert pix is not None and not pix.isNull(), "pymupdf 1페이지 미리보기"
            assert page._original_status.isHidden()
            assert page._original_preview.minimumHeight() >= _ORIGINAL_PREVIEW_MIN
            assert not page._body.isHidden()
            assert page._original_full_mode is False
            page._fit_body_height()
            QApplication.processEvents()
            page._fit_body_height()
            QApplication.processEvents()
            assert page._body.height() > 200
            body_bottom = page._body.geometry().bottom()
            orig_top = page._original_preview.geometry().top()
            assert orig_top > body_bottom, (body_bottom, orig_top, page._body.height())
            assert page._note_scroll.verticalScrollBar().maximum() > 0
            # 전체 보기: 요약은 유지, 버튼만 「미리보기로」
            page._original_full_mode = True
            page._original_preview.hide()
            page._original_full_btn.setText("미리보기로")
            page._original_full_btn.show()
            assert not page._body.isHidden()
            assert page._original_full_btn.text() == "미리보기로"
            page._exit_original_full(restore_preview=True)
            for _ in range(10):
                QApplication.processEvents()
            assert page._original_full_mode is False
            assert not page._body.isHidden()
            assert page._original_full_btn.text() == "전체 보기"
        graph = page._split.widget(0)
        info = page._split.widget(1)
        assert graph.minimumWidth() == 0
        assert info.minimumWidth() == 240
        assert page._chat_host.minimumWidth() == 160  # IdeUnifiedShell iris min
        assert page._splitter.count() == 2
        page.resize(1000, 700)
        page.show()
        QApplication.processEvents()
        sizes = page._splitter.sizes()
        total = sum(sizes)
        assert total > 0
        assert abs(sizes[0] / total - 0.8) < 0.02, sizes
        page._split.resize(1200, 700)
        page._apply_saved_split()
        # 정보 패널은 폭 상한 없이 좌측까지 당길 수 있다.
        assert info.maximumWidth() >= 16777215 or info.maximumWidth() > 1000
        assert page._search.maximumWidth() == 280
        from iris.ui.workspaces.obsidian_workspace_page import _WikiSplitHandle

        assert page._split.handleWidth() == 10
        assert isinstance(page._split.handle(1), _WikiSplitHandle)
        # 구체를 접으면 페이드아웃
        page._split.setSizes([20, 1180])
        page._apply_graph_fade()
        assert page._graph_opacity.opacity() < 0.05
        page._split.setSizes([400, 800])
        page._apply_graph_fade()
        assert page._graph_opacity.opacity() > 0.95
        page._search.setText("security")
        assert page._list.count() == 1
        page.activate_result()
        assert page._title.text() == "Network Security"
        assert page._graph._selected_rel.endswith("network-security.md")
        assert page._graph._aim is not None
        assert page._graph._aim["z1"] > 1.5
        assert any(edge[2] == "link" for edge in page._graph._edges)
        page.hide_results()
    print("wiki self-check ok")


if __name__ == "__main__":
    main()
