"""ChatSession·ChatTurnGate 소유권 자검. Qt 없음."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from iris.runtime.chat_session import ChatSession
from iris.runtime.chat_turn_gate import ChatTurnGate
from iris.storage.conversations import history_dicts
from iris.storage.database import Database


def _check_session(db: Database) -> None:
    session = ChatSession(db)
    assert session.record("user", "안녕") is None
    assert session.history[-1]["content"] == "안녕"
    session.drop_last_user()
    assert session.history == []
    assert history_dicts(db, session.conversation_id) == []

    assert session.record("user", "남겨") is None
    assert session.record("assistant", "응답") is None
    cid = session.conversation_id
    other = session.start_new()
    assert other != cid
    session.activate(other)
    assert session.history == []
    session.activate(cid)
    assert [item["role"] for item in session.history] == ["user", "assistant"]

    session.clear_messages()
    assert session.history == []
    assert history_dicts(db, cid) == []

    err = session.rename(cid, "이름")
    assert err is None
    assert session.title_of(cid) == "이름"


def _check_gate() -> None:
    gate = ChatTurnGate()
    gate.begin("a")
    gate.arm()
    assert gate.is_current("a")
    assert not gate.is_current("b")
    assert gate.busy and not gate.ignore_result

    gate.suppress_result()
    assert gate.consume_ignored()
    assert not gate.consume_ignored()

    gate.begin("b")
    gate.arm()
    finished = gate.finish("b")
    assert finished == "b"
    assert gate.active_id == ""
    assert not gate.busy
    assert not gate.is_current("b")

    gate.begin("c")
    gate.arm()
    # 다른 id로 finish 해도 현재 턴은 남는다.
    stale = gate.finish("nope")
    assert stale == "nope"
    assert gate.active_id == "c"
    assert not gate.busy
    gate.begin("d")
    assert gate.finish(None) == "d"
    assert gate.active_id == ""


def main() -> None:
    tmp = tempfile.mkdtemp()
    db = Database(Path(tmp) / "chat.db")
    try:
        _check_session(db)
    finally:
        db._conn.close()
        shutil.rmtree(tmp, ignore_errors=True)
    _check_gate()
    print("chat ownership ok")


if __name__ == "__main__":
    main()
