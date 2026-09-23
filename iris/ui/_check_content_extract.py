"""ponytail: content_extract + wiki import self-check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.knowledge.content_extract import (
    UnsupportedAttachmentTypeError,
    extract_from_source,
)
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

        bad = root / "payload.bin"
        bad.write_bytes(b"\x00\x01\x02")
        try:
            extract_from_source(str(bad))
            raise AssertionError("expected UnsupportedAttachmentTypeError")
        except UnsupportedAttachmentTypeError as exc:
            assert exc.code == "ATTACHMENT_UNSUPPORTED_TYPE"
            assert "Setup" in str(exc) or "설치" in str(exc)
            assert "허용되지 않는 파일 형식" not in str(exc)

    print("content_extract self-check ok")


if __name__ == "__main__":
    main()
