"""이전 대화 참고 — 검색 범위, 채팅 삭제 시 망각, MainWindow 배선."""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
_APP = QApplication.instance() or QApplication(sys.argv)

from iris.knowledge.history_index import (  # noqa: E402
    OllamaEmbedder,
    forget_conversation,
    index_entry,
    search,
)
from iris.knowledge.history_store import (  # noqa: E402
    KIND_CHAT,
    count_entries,
    record_turn,
    write_episode,
)
from iris.knowledge.iris_wiki import IrisWiki  # noqa: E402
from iris.runtime.chat_run_slot import ChatRunMap  # noqa: E402
from iris.runtime.model_switch import ModelSwitchService  # noqa: E402
from iris.runtime.past_chats import (  # noqa: E402
    MAX_PAST_HITS,
    find_past_chats,
    format_past_chats_for_prompt,
    sources_note,
)
from iris.storage.database import Database  # noqa: E402
from iris.storage.failover_prefs import save_history_settings  # noqa: E402
from iris.ui.window import main_window as mw_module  # noqa: E402
from iris.ui.window.main_window import MainWindow  # noqa: E402


class _Base(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self._tmp.name)
        self.db = Database(root / "p.db")
        self.wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        self.svc = ModelSwitchService(self.db, wiki=self.wiki)

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def _say(self, conv: int, role: str, text: str):
        entry = record_turn(self.db, conv, role, text, wiki=self.wiki)
        assert entry is not None
        index_entry(self.db, entry)
        return entry

    def _set(self, **changes) -> None:
        settings = self.svc.history_settings
        for key, value in changes.items():
            setattr(settings, key, value)
        save_history_settings(self.db, settings)


class FindPastChatsTests(_Base):
    def test_current_conversation_is_left_out(self) -> None:
        """방금 보낸 질문이 자기 자신을 찾아오면 안 된다."""
        self._say(1, "user", "설치 프로그램 권한 오류는 venv 소유권 문제였어요")
        self._say(2, "user", "설치 프로그램 권한 오류 또 났어")
        hits = find_past_chats(self.svc, "설치 프로그램 권한 오류", 2)
        self.assertTrue(hits)
        self.assertTrue(all(h.entry.conversation_id == 1 for h in hits))

    def test_setting_off_finds_nothing(self) -> None:
        self._say(1, "user", "설치 프로그램 권한 오류")
        self._set(reference_past_chats=False)
        self.assertEqual(find_past_chats(self.svc, "설치 프로그램 권한", 2), [])

    def test_short_small_talk_is_not_searched(self) -> None:
        self._say(1, "user", "고마워 정말")
        self.assertEqual(find_past_chats(self.svc, "고마워", 2), [])

    def test_at_most_a_few_records_per_turn(self) -> None:
        for conv in range(1, 9):
            self._say(conv, "user", f"설치 프로그램 권한 오류 {conv}번째")
            self._say(conv, "assistant", f"설치 프로그램 권한은 {conv}번 방법으로 고칩니다")
        self._set(retrieval_limit=20)
        hits = find_past_chats(self.svc, "설치 프로그램 권한 오류", 99)
        self.assertEqual(len(hits), MAX_PAST_HITS)

    def test_prompt_block_tells_the_model_it_is_another_conversation(self) -> None:
        self._say(1, "user", "설치 프로그램 권한 오류")
        block = format_past_chats_for_prompt(find_past_chats(self.svc, "설치 프로그램", 2))
        self.assertIn("예전 대화", block)
        self.assertIn("관련 없으면 무시", block)
        self.assertIn("설치 프로그램 권한 오류", block)

    def test_sources_note_names_what_was_used(self) -> None:
        self._say(1, "user", "설치 프로그램 권한 오류")
        note = sources_note(find_past_chats(self.svc, "설치 프로그램", 2))
        self.assertIn("이전 대화 1건 참고", note)
        self.assertIn("설치 프로그램 권한", note)
        self.assertEqual(sources_note([]), "")


class RelevanceGateTests(TestCase):
    """평소 채팅은 '관련 기록이 있기나 한가'를 판정한다 — 인수인계보다 엄격하다."""

    def _hit(self, body: str, similarity=None):
        from iris.knowledge.history_index import SearchHit
        from iris.knowledge.history_store import HistoryEntry

        entry = HistoryEntry(
            id=1, kind=KIND_CHAT, conversation_id=1, role="user", title="", body=body,
            source="", model="", tags="", rel_path="", created_at="2026-09-29T09:00:00",
        )
        return SearchHit(entry=entry, score=0.0, keyword_rank=1, vector_rank=None, similarity=similarity)

    def test_similar_enough_is_attached(self) -> None:
        from iris.runtime.past_chats import PAST_MIN_SIMILARITY, is_relevant

        self.assertTrue(is_relevant("할당량 소진", self._hit("주간 한도", PAST_MIN_SIMILARITY)))
        self.assertFalse(is_relevant("양자역학", self._hit("마이크를 꺼두고 싶어요", 0.48)))

    def test_one_shared_word_is_not_enough(self) -> None:
        """'저녁' 하나 겹쳤다고 '금요일 저녁 메일 정리'를 붙이면 안 된다(실측 잡음)."""
        from iris.runtime.past_chats import is_relevant

        self.assertFalse(is_relevant("오늘 저녁 뭐 먹을까", self._hit("금요일 저녁마다 편지함 정리")))
        self.assertTrue(is_relevant("설치 프로그램 오류", self._hit("설치 프로그램이 죽어요")))


class ForgetConversationTests(_Base):
    def test_deleting_a_chat_removes_its_history_everywhere(self) -> None:
        a = self._say(1, "user", "지워질 비밀 대화 내용입니다")
        b = self._say(2, "user", "남아야 하는 다른 대화 내용입니다")
        emb = OllamaEmbedder(client=_FakeOllama(), model_name="fake")
        from iris.knowledge.history_index import embed_entry

        embed_entry(self.db, a, emb)
        embed_entry(self.db, b, emb)
        episode = write_episode(self.db, self.wiki, title="비밀 요약", summary="요약본", conversation_id=1)
        assert episode is not None
        day_file = self.wiki.user_root / a.rel_path
        episode_file = self.wiki.user_root / episode.rel_path
        self.assertIn("지워질 비밀", day_file.read_text(encoding="utf-8"))

        removed = forget_conversation(self.db, 1, wiki=self.wiki)

        self.assertEqual(removed, 2)
        self.assertEqual(count_entries(self.db), 1)
        for hits in (search(self.db, "비밀 대화"), search(self.db, "비밀 대화", embedder=emb)):
            self.assertTrue(all(h.entry.conversation_id != 1 for h in hits))
        vectors = self.db._execute("SELECT COUNT(*) AS n FROM wiki_history_vectors").fetchone()
        self.assertEqual(int(vectors["n"]), 1)
        text = day_file.read_text(encoding="utf-8")
        self.assertNotIn("지워질 비밀", text)
        self.assertIn("남아야 하는 다른 대화", text)
        self.assertFalse(episode_file.exists())

    def test_records_outside_any_conversation_are_never_touched(self) -> None:
        self._say(0, "user", "대화 밖 기록")
        self.assertEqual(forget_conversation(self.db, 0, wiki=self.wiki), 0)
        self.assertEqual(count_entries(self.db), 1)


class _FakeOllama:
    def embed(self, model: str, texts: list[str], **kwargs) -> list[list[float]]:
        return [[1.0 if "비밀" in t else 0.0, 1.0] for t in texts]


class _Chat:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def append_message_instant(self, who: str, text: str) -> None:
        self.messages.append((who, text))

    def append_note(self, text: str) -> None:
        self.messages.append(("note", text))


class _SyncWorker:
    """PastChatsWorker 대역 — start() 하면 곧바로 결과를 낸다(또는 안 낸다)."""

    emit_hits = None  # None 이면 끝내 응답하지 않는다(느린 임베딩 흉내)

    def __init__(self, service, base_url, query, conversation_id, *, parent=None, **_kwargs) -> None:
        self._ready = []
        self._failed = []
        self.ready = SimpleNamespace(connect=self._ready.append)
        self.failed = SimpleNamespace(connect=self._failed.append)
        self.query = query
        self.conversation_id = conversation_id

    def start(self) -> None:
        if _SyncWorker.emit_hits is not None:
            for slot in self._ready:
                slot(_SyncWorker.emit_hits)


class _FakeTimer:
    """QTimer 대역 — fire() 로 시간 초과를 직접 일으킨다."""

    last = None

    def __init__(self, parent=None) -> None:
        self._slots = []
        self.stopped = False
        _FakeTimer.last = self

    def setSingleShot(self, on) -> None:  # noqa: N802
        pass

    @property
    def timeout(self):
        return SimpleNamespace(connect=self._slots.append)

    def start(self, ms) -> None:
        self.ms = ms

    def stop(self) -> None:
        self.stopped = True

    def fire(self) -> None:
        for slot in self._slots:
            slot()


class MainWindowPastChatsTests(_Base):
    def setUp(self) -> None:
        super().setUp()
        self.chat = _Chat()
        self.current = {"turn": "t1"}
        runs = ChatRunMap()
        slot = runs.slot(2)
        slot.gate.begin("t1")
        self.win = SimpleNamespace(
            _db=self.db,
            _iris_wiki=self.wiki,
            _model_switch=self.svc,
            _chat=self.chat,
            _conversation_id=2,
            _runs=runs,
            _bound_slot=slot,
            _settings=SimpleNamespace(ollama_base_url="http://127.0.0.1:11434"),
            _pending_past_chats="",
            _past_chats_worker=None,
            _is_current_turn=lambda tid: tid == self.current["turn"],
            _showing_bound=lambda: True,
        )
        self.win._slot_now = lambda: self.win._bound_slot or self.win._runs.slot(2)
        self.win._apply_past_chats = types.MethodType(MainWindow._apply_past_chats, self.win)
        self.turn = SimpleNamespace(id="t1", attachments=())
        self.launched: list[str] = []
        self._patches = [
            patch.object(mw_module, "PastChatsWorker", _SyncWorker),
            patch.object(mw_module, "QTimer", _FakeTimer),
        ]
        for p in self._patches:
            p.start()
        _SyncWorker.emit_hits = None
        self._say(1, "user", "설치 프로그램 권한 오류는 venv 소유권 문제였어요")

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        super().tearDown()

    def _go(self, text: str = "설치 프로그램 권한 오류 또 났어") -> None:
        MainWindow._with_past_chats(
            self.win, self.turn, text, lambda: self.launched.append(self.win._pending_past_chats)
        )

    def test_semantic_result_is_attached_and_shown(self) -> None:
        _SyncWorker.emit_hits = find_past_chats(self.svc, "설치 프로그램 권한", 2)
        self._go()
        self.assertEqual(len(self.launched), 1)
        self.assertIn("venv 소유권", self.launched[0])
        self.assertEqual(self.chat.messages[0][0], "note")  # Iris 답변이 아니다
        self.assertIn("이전 대화 1건 참고", self.chat.messages[0][1])
        self.assertTrue(_FakeTimer.last.stopped)

    def test_slow_embedding_falls_back_to_keywords_once(self) -> None:
        self._go()
        self.assertEqual(self.launched, [])  # 아직 기다리는 중
        _FakeTimer.last.fire()
        self.assertEqual(len(self.launched), 1)
        self.assertIn("venv 소유권", self.launched[0])
        _FakeTimer.last.fire()  # 두 번 보내면 안 된다
        self.assertEqual(len(self.launched), 1)

    def test_stopped_turn_is_not_sent(self) -> None:
        self._go()
        self.win._runs.slot(2).gate.finish("t1")
        _FakeTimer.last.fire()
        self.assertEqual(self.launched, [])

    def test_nothing_found_sends_without_a_note(self) -> None:
        _SyncWorker.emit_hits = []
        self._go()
        self.assertEqual(self.launched, [""])
        self.assertEqual(self.chat.messages, [])

    def test_setting_off_sends_immediately(self) -> None:
        self._set(reference_past_chats=False)
        _FakeTimer.last = None
        self._go()
        self.assertEqual(self.launched, [""])
        self.assertIsNone(_FakeTimer.last)

    def test_past_block_sits_right_before_the_users_message(self) -> None:
        win = SimpleNamespace(
            _history=[
                {"role": "user", "content": "앞 질문"},
                {"role": "assistant", "content": "앞 답"},
                {"role": "user", "content": "지금 질문"},
            ],
            _db=self.db,
            _pending_handoff="",
            _pending_past_chats="# 이전 대화에서 찾은 기록",
            _use_hermes_backend=lambda: True,
        )
        payload = MainWindow._chat_messages_with_project_context(win)
        self.assertEqual(payload[-1]["content"], "지금 질문")
        self.assertEqual(payload[-2], {"role": "system", "content": "# 이전 대화에서 찾은 기록"})
        self.assertEqual(payload[0]["role"], "system")


class EmbedWarmupTests(_Base):
    """입력하는 동안 임베딩 모델을 미리 깨운다 — 콜드 로드(실측 9초)를 보낼 때 안 타게."""

    def test_warmup_loads_the_model_and_holds_it(self) -> None:
        from iris.runtime.model_switch import EMBED_KEEP_ALIVE
        from iris.runtime.past_chats import warm_embedder

        calls = []

        class _Client:
            def pick_embedding_model(self, preferred=""):
                return "bge-m3:latest"

            def embed(self, model, texts, **kwargs):
                calls.append((model, texts, kwargs))
                return [[1.0]]

        self.assertEqual(warm_embedder(self.svc, _Client()), "bge-m3:latest")
        self.assertEqual(calls[0][2], {"keep_alive": EMBED_KEEP_ALIVE})

    def test_warmup_does_nothing_when_past_chats_are_off(self) -> None:
        from iris.runtime.past_chats import warm_embedder

        self._set(reference_past_chats=False)
        self.assertEqual(warm_embedder(self.svc, object()), "")

    def test_client_sends_keep_alive_so_ollama_does_not_unload_after_5_minutes(self) -> None:
        from iris.infrastructure.ollama_client import OllamaClient

        sent = []
        client = OllamaClient("http://127.0.0.1:11434")
        client._post_json = lambda path, body, **kw: (sent.append(body), {"embeddings": [[0.1]]})[1]
        client.embed("bge-m3", ["x"], keep_alive="30m")
        client.embed("bge-m3", ["x"])
        self.assertEqual(sent[0]["keep_alive"], "30m")
        self.assertNotIn("keep_alive", sent[1])

    def test_keystrokes_start_one_warmup_until_the_interval_passes(self) -> None:
        started = []

        class _Worker:
            def __init__(self, service, base_url, *, parent=None):
                self.running = True

            def isRunning(self):  # noqa: N802
                return self.running

            def start(self):
                started.append(self)

        win = SimpleNamespace(
            _embed_warm_worker=None,
            _embed_warmed_at=0.0,
            _model_switch=self.svc,
            _settings=SimpleNamespace(ollama_base_url="http://127.0.0.1:11434"),
        )
        with patch.object(mw_module, "EmbedWarmupWorker", _Worker):
            for _ in range(5):  # 글자마다 불린다
                MainWindow._warm_embedder_soon(win)
            self.assertEqual(len(started), 1)
            started[0].running = False  # 끝났어도 간격 안에서는 다시 안 깨운다
            MainWindow._warm_embedder_soon(win)
            self.assertEqual(len(started), 1)
            win._embed_warmed_at -= mw_module._EMBED_REWARM_SEC + 1
            MainWindow._warm_embedder_soon(win)
            self.assertEqual(len(started), 2)


class ComposingSignalTests(TestCase):
    def test_typing_emits_composing_but_clearing_does_not(self) -> None:
        from iris.ui.chat.chat_panel import ChatPanel

        panel = ChatPanel()
        fired = []
        panel.composing.connect(lambda: fired.append(1))
        panel._input.setPlainText("저번에")
        self.assertEqual(len(fired), 1)
        panel._input.setPlainText("")
        self.assertEqual(len(fired), 1)


class NoteLineTests(TestCase):
    """앱 안내 줄은 Iris 답변이 아니다 — [재생]·TTS 등록·마크다운 기호가 없어야 한다."""

    def test_note_has_no_play_link_and_is_not_read_aloud(self) -> None:
        from iris.ui.chat.chat_panel import ChatPanel

        panel = ChatPanel()
        panel.append_message_instant("Iris", "진짜 답변입니다")
        before = panel.message_body("last")
        panel.append_note("이전 대화 1건 참고 — 9/29 「robocopy 로 바꾸니까 설치 됐어요!」")
        html_text = panel._log.toHtml()
        plain = panel._log.toPlainText()
        self.assertIn("이전 대화 1건 참고", plain)
        self.assertEqual(html_text.count("iris-tts://"), before and 1)  # 답변 1개 몫뿐
        self.assertEqual(panel.message_body("last"), before)
        self.assertNotIn("Iris: 이전 대화", plain)

    def test_note_escapes_html(self) -> None:
        from iris.ui.chat.chat_panel import ChatPanel

        panel = ChatPanel()
        panel.append_note("「<b>굵게</b>」")
        self.assertIn("<b>굵게</b>", panel._log.toPlainText())

    def test_sources_note_has_no_markdown_underscores(self) -> None:
        from iris.knowledge.history_index import SearchHit
        from iris.knowledge.history_store import HistoryEntry

        entry = HistoryEntry(
            id=1, kind=KIND_CHAT, conversation_id=1, role="user", title="", body="설치 오류",
            source="", model="", tags="", rel_path="", created_at="2026-09-29T09:00:00",
        )
        note = sources_note([SearchHit(entry=entry, score=0.0, keyword_rank=1, vector_rank=None)])
        self.assertFalse(note.startswith("_") or note.endswith("_"))


class InterruptedTitleTests(TestCase):
    """답변 중 대화를 옮겨도 제목이 '대화 전환으로 응답을 중단했습니다.'가 되면 안 된다."""

    def test_interrupted_note_alone_never_becomes_the_title(self) -> None:
        from iris.storage.conversations import DEFAULT_TITLE, INTERRUPTED_NOTE, suggest_title

        msgs = [{"role": "user", "content": "설치 오류 고쳐줘"},
                {"role": "assistant", "content": INTERRUPTED_NOTE}]
        self.assertEqual(suggest_title(msgs), DEFAULT_TITLE)

    def test_earlier_title_is_not_overwritten_by_the_interruption(self) -> None:
        from iris.storage.conversations import INTERRUPTED_NOTE, suggest_title

        msgs = [{"role": "user", "content": "설치 오류 고쳐줘"},
                {"role": "assistant", "content": "robocopy 로 폴더를 비우면 됩니다. 이유는…"},
                {"role": "user", "content": "또 났어"},
                {"role": "assistant", "content": INTERRUPTED_NOTE}]
        self.assertEqual(suggest_title(msgs), "robocopy 로 폴더를 비우면 됩니다.")

    def test_partial_answer_still_names_the_chat(self) -> None:
        from iris.storage.conversations import INTERRUPTED_NOTE, suggest_title

        msgs = [{"role": "user", "content": "질문"},
                {"role": "assistant", "content": "venv 를 지우고 다시 만드세요.\n\n" + INTERRUPTED_NOTE}]
        self.assertEqual(suggest_title(msgs), "venv 를 지우고 다시 만드세요.")

    def test_title_in_the_real_database_after_a_switch(self) -> None:
        """저장까지 거친 실제 경로 — 이번에 앱에서 본 증상 그대로."""
        from iris.storage.conversations import (
            DEFAULT_TITLE,
            INTERRUPTED_NOTE,
            append_message,
            create_conversation,
            get_conversation,
        )

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Database(Path(tmp) / "t.db")
            conv = create_conversation(db)
            append_message(db, conv.id, "user", "저번에 설치 오류 어떻게 고쳤지?")
            append_message(db, conv.id, "assistant", INTERRUPTED_NOTE)
            self.assertEqual(get_conversation(db, conv.id).title, DEFAULT_TITLE)
            db.close()


class DamagedTitleRepairTests(TestCase):
    def test_titles_left_by_the_old_bug_are_reset_but_user_titles_stay(self) -> None:
        from iris.storage.conversations import (
            DEFAULT_TITLE,
            INTERRUPTED_NOTE,
            create_conversation,
            ensure_chat_schema,
            get_conversation,
        )

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Database(Path(tmp) / "t.db")
            damaged = create_conversation(db)
            renamed = create_conversation(db)
            # 예전 버전이 남긴 제목 / 사용자가 일부러 같은 이름을 붙인 경우
            db._execute("UPDATE chat_conversations SET title = ? WHERE id = ?", (INTERRUPTED_NOTE, damaged.id))
            db._execute(
                "UPDATE chat_conversations SET title = ?, title_locked = 1 WHERE id = ?",
                (INTERRUPTED_NOTE, renamed.id),
            )
            db._commit()
            ensure_chat_schema(db)  # 앱이 DB를 열 때
            self.assertEqual(get_conversation(db, damaged.id).title, DEFAULT_TITLE)
            self.assertEqual(get_conversation(db, renamed.id).title, INTERRUPTED_NOTE)
            db.close()


class QuestionAnswerPairTests(_Base):
    """질문만 걸리면 쓸 게 없다 — 같은 대화의 답을 붙이고, 답 없는 되풀이는 버린다."""

    def test_same_question_without_an_answer_is_dropped(self) -> None:
        """앱에서 실제로 본 증상: 다른 테스트 채팅의 똑같은 질문(답 없음)을 찾아왔다."""
        from iris.storage.conversations import INTERRUPTED_NOTE

        self._say(3, "user", "저번에 설치 오류 어떻게 고쳤지?")
        self._say(3, "assistant", INTERRUPTED_NOTE)
        self.assertEqual(find_past_chats(self.svc, "저번에 설치 오류 어떻게 고쳤지?", 9), [])

    def test_question_brings_its_answer(self) -> None:
        self._say(1, "user", "설치 프로그램이 Access Denied 로 죽어요")
        self._say(1, "assistant", "python.exe 가 잠겨 있으니 robocopy 로 폴더를 비우세요")
        chats = find_past_chats(self.svc, "설치 프로그램 Access Denied", 9)
        self.assertEqual(len(chats), 1)
        block = format_past_chats_for_prompt(chats)
        self.assertIn("사용자: 설치 프로그램이 Access Denied", block)
        self.assertIn("아이리스: python.exe 가 잠겨", block)

    def test_answer_brings_its_question_and_pairs_are_not_doubled(self) -> None:
        self._say(1, "user", "설치 프로그램 권한 문제 어떻게 해")
        self._say(1, "assistant", "설치 프로그램 권한은 venv 소유권을 고치면 됩니다")
        chats = find_past_chats(self.svc, "설치 프로그램 권한", 9)
        self.assertEqual(len(chats), 1)  # 질문·답이 둘 다 걸려도 한 쌍
        self.assertIsNotNone(chats[0].question)
        self.assertIsNotNone(chats[0].answer)
        self.assertIn("설치 프로그램 권한 문제", sources_note(chats))

    def test_informative_user_line_without_answer_is_kept(self) -> None:
        """답이 없어도 정보가 있는 사용자 말은 남긴다(질문을 품고 있어도)."""
        self._say(1, "user", "설치 프로그램 권한 오류는 robocopy 로 바꾸니까 해결됐어요")
        chats = find_past_chats(self.svc, "설치 프로그램 권한 오류", 9)
        self.assertEqual(len(chats), 1)
        self.assertIsNone(chats[0].answer)

    def test_interrupted_answer_is_not_used_as_an_answer(self) -> None:
        from iris.storage.conversations import INTERRUPTED_NOTE

        self._say(1, "user", "설치 프로그램 권한 오류는 venv 문제였나")
        self._say(1, "assistant", INTERRUPTED_NOTE)
        chats = find_past_chats(self.svc, "설치 프로그램 권한 오류", 9)
        for chat in chats:
            self.assertIsNone(chat.answer)
        self.assertNotIn(INTERRUPTED_NOTE, format_past_chats_for_prompt(chats))


class SurroundingTurnTests(_Base):
    def test_follow_up_line_brings_the_answer_before_it(self) -> None:
        """앱에서 본 경우: 걸린 건 '됐어요!' 후속 말, 해결법은 그 앞 답에 있었다."""
        self._say(1, "user", "Access Denied 로 죽어요")
        self._say(1, "assistant", "python.exe 가 잠겨 있으니 폴더 삭제를 바꾸세요")
        self._say(1, "user", "robocopy 로 바꾸니까 설치 됐어요")
        chats = find_past_chats(self.svc, "robocopy 설치 됐어요", 9)
        self.assertEqual(len(chats), 1)
        block = format_past_chats_for_prompt(chats)
        self.assertLess(block.index("python.exe 가 잠겨"), block.index("robocopy 로 바꾸니까"))

    def test_overlapping_windows_are_not_attached_twice(self) -> None:
        self._say(1, "user", "설치 프로그램 권한 오류 어떻게 해")
        self._say(1, "assistant", "설치 프로그램 권한은 venv 소유권 문제")
        self._say(1, "user", "설치 프로그램 권한 고쳤더니 됐어요")
        chats = find_past_chats(self.svc, "설치 프로그램 권한", 9)
        ids = [t.id for c in chats for t in c.turns]
        self.assertEqual(len(ids), len(set(ids)))
