"""T4: H1 WritingPart card — edit + Save → Python drain → DB parts update."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from iris.core.message_parts import (
    TextPart,
    WritingPart,
    parts_for_model,
    writing_context_snippets,
)
from iris.storage.conversations import (
    append_message,
    create_conversation,
    get_message,
    message_parts,
    update_message_parts,
)
from iris.storage.database import Database
from iris.ui.chat.transcript_h1 import H1TranscriptHost
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

_EDIT_AND_SAVE_JS = r"""
(function() {
  var card = document.querySelector('.writing-card');
  if (!card) return JSON.stringify({ok: false, detail: 'no writing card'});
  var title = card.querySelector('.writing-title');
  var body = card.querySelector('.writing-body');
  var save = card.querySelector('.writing-save');
  if (!(title && body && save)) {
    return JSON.stringify({ok: false, detail: 'missing inputs'});
  }
  title.value = 'Edited Title';
  body.value = 'Edited body for next turn.';
  save.click();
  return JSON.stringify({
    ok: true,
    savedAttr: card.getAttribute('data-saved') === '1',
    btnSaved: save.getAttribute('data-saved') === '1',
    title: title.value,
    body: body.value,
    queueLen: (window.__irisWritingUpdates || []).length
  });
})()
"""


def _run_js(view, script: str, timeout_ms: int = 10000):
    box: dict = {"raw": None, "done": False}
    loop = QEventLoop()

    def _cb(raw) -> None:
        box["raw"] = raw
        box["done"] = True
        loop.quit()

    view.page().runJavaScript(script, _cb)
    QTimer.singleShot(timeout_ms, loop.quit)
    if not box["done"]:
        loop.exec()
    return box["raw"]


def _check_writing_card(app: QApplication) -> None:
    _ = app
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    try:
        db_path = Path(tmp.name) / "writing.db"
        db = Database(db_path)
        conv = create_conversation(db)
        original = [
            TextPart(markdown="Draft intro"),
            WritingPart(title="Draft Title", body="Original body"),
        ]
        mid = append_message(db, conv.id, "assistant", "", parts=original)
        msg_id = str(mid)

        host = H1TranscriptHost()
        host.resize(640, 720)
        view = host.view()
        assert view is not None

        # Connect before append so we do not miss loadFinished.
        loaded = {"ok": False, "done": False}
        loop = QEventLoop()

        def _on_finished(ok: bool) -> None:
            loaded["ok"] = bool(ok)
            loaded["done"] = True
            loop.quit()

        view.loadFinished.connect(_on_finished)
        host.append_turn("assistant", original, msg_id=msg_id)
        QTimer.singleShot(15000, loop.quit)
        if not loaded["done"]:
            loop.exec()
        try:
            view.loadFinished.disconnect(_on_finished)
        except TypeError:
            pass
        assert loaded["done"] and loaded["ok"], "writing card setHtml loadFinished failed"

        settle = QEventLoop()
        QTimer.singleShot(300, settle.quit)
        settle.exec()

        raw = _run_js(view, _EDIT_AND_SAVE_JS)
        assert raw is not None, "edit/save runJavaScript returned None"
        probe = json.loads(raw) if isinstance(raw, str) else raw
        assert isinstance(probe, dict) and probe.get("ok"), f"edit/save: {probe}"
        assert probe.get("savedAttr") and probe.get("btnSaved"), f"save flags: {probe}"
        assert int(probe.get("queueLen") or 0) >= 1, f"queue empty: {probe}"

        updates = host.take_writing_updates()
        assert len(updates) >= 1, f"no updates drained: {updates}"
        upd = updates[0]
        assert upd.get("msg_id") == msg_id, f"msg_id: {upd}"
        assert int(upd.get("part_index", -1)) == 1, f"part_index: {upd}"
        assert upd.get("title") == "Edited Title", f"title: {upd}"
        assert upd.get("body") == "Edited body for next turn.", f"body: {upd}"

        mem = host.parts_for_message(msg_id)
        assert len(mem) == 2 and isinstance(mem[1], WritingPart)
        assert mem[1].title == "Edited Title"
        assert mem[1].body == "Edited body for next turn."

        update_message_parts(db, mid, mem)
        db.close()

        db2 = Database(db_path)
        again = get_message(db2, mid)
        assert again is not None
        loaded_parts = message_parts(again)
        assert isinstance(loaded_parts[1], WritingPart)
        assert loaded_parts[1].title == "Edited Title"
        assert loaded_parts[1].body == "Edited body for next turn."
        assert "Edited body for next turn." in (again.content or "")
        snippets = writing_context_snippets(loaded_parts)
        assert "Edited Title" in snippets and "Edited body for next turn." in snippets
        model_text = parts_for_model(loaded_parts)
        assert "Edited body for next turn." in model_text
        db2.close()
        print(
            "transcript_writing probe ok",
            json.dumps(
                {
                    "msg_id": msg_id,
                    "title": upd.get("title"),
                    "body": upd.get("body"),
                    "snippets_ok": True,
                },
                ensure_ascii=False,
            ),
        )
    finally:
        tmp.cleanup()


def main() -> int:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    _check_writing_card(app)
    print("transcript_writing ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
