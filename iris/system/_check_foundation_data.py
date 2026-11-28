"""Disposable pre-migration data and extension used by the owned-slot check."""

from contextlib import closing
from hashlib import sha256
from pathlib import Path
from shutil import copyfile
from sqlite3 import connect
from tempfile import TemporaryDirectory

from iris.mcp.native_manager import NativeMCPManager
from iris.runtime.chat_session import ChatSession
from iris.runtime.turn_todo import TurnTodoStore
from iris.storage.conversations import list_messages, message_parts
from iris.storage.database import Database
from iris.storage.gateway import GatewayStore
from iris.storage.memory import MemoryStore
from iris.system.execution_context import ExecutionContext


_CONTEXT = ExecutionContext(principal="foundation", session_id="prior-session")
_MARKER = "FOUNDATION DATA 1287"


def prepare(root: Path) -> dict[str, str]:
    root.mkdir()
    original = root / "old.db"
    with closing(connect(original)) as db:
        db.executescript("""
            CREATE TABLE chat_conversations (
                id INTEGER PRIMARY KEY, title TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE chat_messages (
                id INTEGER PRIMARY KEY, conversation_id INTEGER, role TEXT, content TEXT, created_at TEXT
            );
            INSERT INTO chat_conversations VALUES (1, 'Legacy title', '2025-01-01', '2025-01-01');
            INSERT INTO chat_messages VALUES (1, 1, 'user', 'Legacy message', '2025-01-01');
        """)
    copyfile(original, root / "desktop.db")
    attached = root / "attachment.txt"
    attached.write_text(_MARKER, encoding="utf-8")
    with closing(Database(root / "desktop.db")) as db:
        chat = ChatSession(db)
        chat.activate(1)
        chat.attachments.attach([str(attached)])
        chat.persist_attachments()
        assert chat.record("assistant", _MARKER, model_content="private model context") is None
        memory = MemoryStore(db)
        memory.set_enabled(_CONTEXT, True)
        record = memory.create(_CONTEXT, "user", "fact", _MARKER)
    todo = TurnTodoStore(_CONTEXT.session_id, persist_dir=root)
    todo.upsert("legacy-task", _MARKER)
    with closing(GatewayStore(root / "gateway.db", max_events=16)) as gateway:
        cid = gateway.start("legacy-run", "legacy-gateway", _CONTEXT.principal, new_session=True)
        gateway.publish("legacy-run", 1, {"type": "delta", "text": _MARKER})
        gateway.publish("legacy-run", 2, {"type": "finished", "text": _MARKER},
                        finished_turn=(cid, "Legacy question", _MARKER))
    NativeMCPManager(home=root.parent).register("foundation-disabled", {
        "url": "http://127.0.0.1:1/", "enabled": False,
    })
    return {"original_sha256": sha256(original.read_bytes()).hexdigest(), "memory_id": record["id"]}


def verify(root: Path, expected: dict[str, str]) -> None:
    with closing(Database(root / "desktop.db")) as db:
        chat = ChatSession(db)
        assert chat.conversation_id == 1
        assert [row["content"] for row in chat.history] == ["Legacy message", _MARKER]
        assert message_parts(list_messages(db, 1)[0])[0].markdown == "Legacy message"
        assert chat.history[1]["model_content"] == "private model context"
        [(aid, *_)] = chat.attachments.references()
        assert chat.attachments.resolve_file(aid).read_text(encoding="utf-8") == _MARKER
        assert MemoryStore(db).get(_CONTEXT, expected["memory_id"])["content"] == _MARKER
    assert TurnTodoStore.load(_CONTEXT.session_id, persist_dir=root).read_one("legacy-task").content == _MARKER
    with closing(GatewayStore(root / "gateway.db", max_events=16)) as gateway:
        assert gateway.run("legacy-run", _CONTEXT.principal)["status"] == "finished"
        assert gateway.history("legacy-gateway", _CONTEXT.principal)[-1]["content"] == _MARKER
        assert [(e["seq"], e["type"]) for e in gateway.events("legacy-run", 0)] == [
            (1, "delta"), (2, "finished"),
        ]
    assert NativeMCPManager(home=root.parent).catalog() == [
        {"name": "foundation-disabled", "status": "disabled", "transport": "http"},
    ]
    assert sha256((root / "old.db").read_bytes()).hexdigest() == expected["original_sha256"]


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        root = Path(directory) / "compatibility"
        verify(root, prepare(root))
    print("foundation data compatibility ok")
