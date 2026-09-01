"""ponytail: wiki save intent parsing self-check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.knowledge.wiki_save_intent import (
    is_wiki_save_intent,
    parse_wiki_save_request,
    wants_summarize,
)


def main() -> None:
    assert is_wiki_save_intent("이 pdf 위키에 저장해줘")
    assert wants_summarize("링크 요약해서 위키에 저장")
    assert not wants_summarize("위키에 저장")

    with tempfile.TemporaryDirectory() as tmp:
        note = Path(tmp) / "demo.md"
        note.write_text("hello", encoding="utf-8")
        req = parse_wiki_save_request(
            "위키에 저장해줘",
            [str(note)],
        )
        assert req is not None
        assert req.source.endswith("demo.md")
        assert req.mode == "raw"

    req2 = parse_wiki_save_request(
        "https://example.com 문서 정리해서 위키에 저장",
        [],
    )
    assert req2 is not None
    assert req2.source.startswith("https://")
    assert req2.mode == "summarize"

    print("wiki_save_intent self-check ok")


if __name__ == "__main__":
    main()
