"""apple.txt 경로 거절과 붙여넣기 분기. 클립보드 원문은 출력하지 않는다."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMimeData, QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from iris.system.project_ops import workspace_rel_for_open  # noqa: E402
from iris.ui.chat.chat_display import assistant_visible_text  # noqa: E402
from iris.ui.chat.chat_panel import _drop_targets_from_mime  # noqa: E402


def check_workspace_paths() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "apple.txt").write_text("a", encoding="utf-8")
        assert workspace_rel_for_open(root, "apple.txt") == "apple.txt"
        assert workspace_rel_for_open(root, str(root / "apple.txt")) == "apple.txt"
        other = os.path.normcase(str(root / "apple.txt"))
        assert workspace_rel_for_open(root, other) == "apple.txt"
        for bad in ("../outside.txt", str(root.parent / "outside.txt")):
            try:
                workspace_rel_for_open(root, bad)
            except ValueError as exc:
                assert "escapes" in str(exc)
            else:
                raise AssertionError(bad)


def check_folder_sentence() -> None:
    shown = assistant_visible_text("현재 작업 공간을 C:/Users/kwakm 로 지정", streaming=False)
    assert "Users" not in shown and "kwakm" not in shown
    assert "작업 폴더" in shown and "로 지정" in shown, shown


def _branch(mime: QMimeData) -> str:
    formats = [str(item) for item in mime.formats()]
    file_urls = _drop_targets_from_mime(mime, text_paths=False)
    text_as_file = _drop_targets_from_mime(mime, text_paths=True)
    if file_urls:
        kind = "attach-file"
    elif text_as_file and not file_urls:
        kind = "text-not-file"
    else:
        kind = "insert-text"
    print(f"paste branch={kind} formats={formats}")
    return kind


def check_paste_branches() -> None:
    app = QApplication.instance() or QApplication([])
    sentence = QMimeData()
    sentence.setText("일반 문장입니다.")
    assert _branch(sentence) == "text-not-file"

    code = QMimeData()
    code.setText("```python\nprint(1)\n```")
    assert _branch(code) == "insert-text"

    path_in_code = QMimeData()
    path_in_code.setText("iris/ui/chat/chat_panel.py")
    assert _branch(path_in_code) == "text-not-file"

    path_text = QMimeData()
    path_text.setText("C:/Users/kwakm/apple.txt")
    assert _branch(path_text) == "text-not-file"

    real = QMimeData()
    real.setUrls([QUrl.fromLocalFile("C:/Users/kwakm/apple.txt")])
    assert _branch(real) == "attach-file"
    assert app is not None


def main() -> None:
    check_workspace_paths()
    check_folder_sentence()
    check_paste_branches()
    print("open path / paste branch ok")


if __name__ == "__main__":
    main()
