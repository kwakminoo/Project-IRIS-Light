"""ponytail: Iris Wiki write / slug / inbox self-check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.knowledge.iris_wiki import IrisWiki, slugify_note_name


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

    print("wiki self-check ok")


if __name__ == "__main__":
    main()
