"""LLM 제목 실패 시 휴리스틱만 저장하고, 활동줄 실패 문구를 쓰지 않는다."""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path

from iris.storage.chat_title import apply_heuristic_title
from iris.storage.conversations import (
    DEFAULT_TITLE,
    append_message,
    create_conversation,
    list_messages,
    load_title_basis,
    suggest_title,
)
from iris.storage.database import Database
from iris.ui.window.main_window import MainWindow


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Database(Path(tmp) / "t.db")
        try:
            conv = create_conversation(db, title=DEFAULT_TITLE)
            append_message(db, conv.id, "user", "프랜스포머는 뭔지 아는데 어탠션은뭐야?")
            append_message(
                db,
                conv.id,
                "assistant",
                "어텐션은 각 토큰이 서로를 보는 방식입니다. 트랜스포머의 핵심입니다.",
            )

            title = apply_heuristic_title(db, conv.id)
            assert title and title != DEFAULT_TITLE, title
            expected = suggest_title(
                list_messages(db, conv.id), basis=load_title_basis(db)
            )
            assert title == expected, (title, expected)
        finally:
            db.close()

    # 실패·시작·저장 예외 슬롯에 활동줄 제목 실패 문구를 넣지 않는다
    failed_src = inspect.getsource(MainWindow._on_chat_title_failed)
    request_src = inspect.getsource(MainWindow._request_chat_title)
    ready_src = inspect.getsource(MainWindow._on_chat_title_ready)
    for banned in (
        "채팅 제목 실패",
        "채팅 제목을 요청하지 못했습니다",
        "채팅 제목 저장 실패",
    ):
        assert banned not in failed_src, banned
        assert banned not in request_src, banned
        assert banned not in ready_src, banned

    print("chat_title_fallback self-check ok")


if __name__ == "__main__":
    main()
