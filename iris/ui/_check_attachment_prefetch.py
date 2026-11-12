"""Composer prefetch fingerprint + worker path ordering."""

from __future__ import annotations

import inspect

from iris.ui.window.main_window import MainWindow


def main() -> None:
    fp = MainWindow._attachment_paths_fingerprint
    assert callable(fp)
    empty = fp(())
    assert empty == ""

    body = inspect.getsource(MainWindow._execute_user_turn_body)
    assert "_attach_prefetch_prepared" in body
    assert "첨부 읽는 중" in body
    assert "_sync_voice_conversation_state" in body
    assert body.index("_present_user_turn_early") < body.index("AttachmentWorker")

    composer = inspect.getsource(MainWindow._on_composer_files)
    assert "_start_attachment_prefetch" in composer
    print("attachment prefetch ok")


if __name__ == "__main__":
    main()
