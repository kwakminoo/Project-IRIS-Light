"""ponytail: content_extract + wiki import self-check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.knowledge.content_extract import extract_from_source
from iris.knowledge.iris_wiki import IrisWiki


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        wiki_root = root / "wiki"
        wiki = IrisWiki(docs_root=root / "docs", user_root=wiki_root)

        note = root / "sample.md"
        note.write_text("# Demo\n\nHello wiki import.", encoding="utf-8")
        out = extract_from_source(str(note))
        assert out["kind"] == "text"
        assert "Hello wiki import" in str(out["text"])

        path, rel = wiki.write_inbox_note(
            str(out["title"]),
            str(out["text"]),
            source_url=str(out["source"]),
        )
        assert rel.endswith(".md")
        assert path.is_file()

    print("content_extract self-check ok")


if __name__ == "__main__":
    main()
