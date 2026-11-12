"""턴 전 컨텍스트 워커 + SpeakTool 의미검색 헬퍼.

MainWindow 의 PastChatsWorker 는 위키·오늘웹·코드 노트를 UI 밖에서 모은다.
이전 대화 자동 주입은 끈다 (`search_past=False`).

SpeakTool `chat.search_past` 는 `run_semantic_past_search_off_ui` 로
`semantic_past_chats` 만 돌린다. 키워드-only 폴백 없음.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QEventLoop, QThread, QTimer, pyqtSignal

from iris.infrastructure.ollama_client import OllamaClient
from iris.runtime.past_chats import find_past_chats, semantic_past_chats, warm_embedder

# SpeakTool sync wait — embed cold start can be ~9s; keep UI event loop pumping.
SEARCH_PAST_TIMEOUT_S = 12.0


def run_semantic_past_search_off_ui(
    service: object,
    base_url: str,
    query: str,
    conversation_id: int,
    *,
    limit: int | None = None,
    timeout_s: float = SEARCH_PAST_TIMEOUT_S,
) -> tuple[list, str | None]:
    """Run `semantic_past_chats` off the caller thread; wait via QEventLoop.

    Returns (chats, message). On timeout/failure: empty chats + message.
    Never falls back to keyword-only.
    """
    box: dict[str, object] = {"chats": [], "message": None}

    def work() -> None:
        try:
            chats, msg = semantic_past_chats(
                service,
                query,
                conversation_id,
                OllamaClient(base_url),
                limit=limit,
            )
            box["chats"] = chats
            box["message"] = msg
        except Exception as exc:  # noqa: BLE001
            box["chats"] = []
            box["message"] = f"semantic search failed: {exc}"

    pool = ThreadPoolExecutor(max_workers=1)
    fut = pool.submit(work)
    loop = QEventLoop()
    timed_out = {"v": False}

    def poll() -> None:
        if fut.done():
            loop.quit()
        else:
            QTimer.singleShot(50, poll)

    def on_timeout() -> None:
        timed_out["v"] = True
        loop.quit()

    wait_ms = max(1, int(float(timeout_s) * 1000))
    QTimer.singleShot(wait_ms, on_timeout)
    QTimer.singleShot(0, poll)
    loop.exec()
    if timed_out["v"] and not fut.done():
        pool.shutdown(wait=False, cancel_futures=True)
        return [], "semantic search timed out"
    pool.shutdown(wait=True)
    chats = box["chats"]
    msg = box["message"]
    return list(chats or []), (str(msg) if msg else None)


class PastChatsWorker(QThread):
    # list[SearchHit]
    ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        service: object,
        base_url: str,
        query: str,
        current_conversation_id: int,
        *,
        search_today: bool = False,
        search_past: bool = False,
        wiki_on_empty: bool = False,
        code_on_empty: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._base_url = base_url
        self._query = query
        self._conversation_id = int(current_conversation_id or 0)
        self._search_today = bool(search_today)
        self._search_past = bool(search_past)
        self._wiki_on_empty = bool(wiki_on_empty)
        self._code_on_empty = bool(code_on_empty)

    def run(self) -> None:
        web = ""
        web_urls: list[str] = []
        if self._search_today:
            try:
                from iris.knowledge.answer_grounding import today_search

                found = today_search(self._query)
            except Exception as exc:  # noqa: BLE001
                from iris.knowledge.answer_grounding import search_failure_reply

                self.ready.emit(
                    {
                        "past": [],
                        "wiki": "",
                        "code": "",
                        "web_error": True,
                        "web": search_failure_reply(str(exc)[:200], self._query),
                        "web_urls": [],
                    }
                )
                return
            if not found.ok:
                self.ready.emit(
                    {
                        "past": [],
                        "wiki": "",
                        "code": "",
                        "web_error": True,
                        "web": found.reply,
                        "web_urls": [],
                    }
                )
                return
            web = found.evidence
            web_urls = list(found.urls)
        try:
            client = OllamaClient(self._base_url)
            hits: list = []
            if self._search_past:
                hits = find_past_chats(
                    self._service,
                    self._query,
                    self._conversation_id,
                    client,
                )
            wiki_block = ""
            code_block = ""
            wiki = getattr(self._service, "wiki", None)
            if wiki is not None and not self._search_today:
                from iris.knowledge.code_note_prompt import code_prompt_for_query
                from iris.knowledge.wiki_note_index import wiki_prompt_for_query
                from iris.runtime.model_switch import resolve_embedder

                embedder = resolve_embedder(self._service.history_settings, client)
                wiki_block = wiki_prompt_for_query(
                    self._service.db,
                    wiki,
                    self._query,
                    embedder,
                    on_empty=self._wiki_on_empty,
                )
                if self._code_on_empty:
                    code_block = code_prompt_for_query(
                        wiki._docs.root,
                        self._query,
                        on_empty=True,
                    )
        except Exception as exc:  # noqa: BLE001
            if web:
                self.ready.emit(
                    {
                        "past": [],
                        "wiki": "",
                        "code": "",
                        "web_error": False,
                        "web": web,
                        "web_urls": web_urls,
                    }
                )
                return
            self.failed.emit(str(exc))
            return
        self.ready.emit(
            {
                "past": list(hits),
                "wiki": wiki_block,
                "code": code_block,
                "web_error": False,
                "web": web,
                "web_urls": web_urls,
            }
        )


class EmbedWarmupWorker(QThread):
    """입력하는 동안 임베딩 모델을 미리 깨운다. 실패해도 조용히 끝난다."""

    # (올린 모델 이름 — 비었으면 할 일이 없었다)
    finished_ok = pyqtSignal(str)

    def __init__(self, service: object, base_url: str, *, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._base_url = base_url

    def run(self) -> None:
        try:
            model = warm_embedder(self._service, OllamaClient(self._base_url))
        except Exception:  # noqa: BLE001
            model = ""
        self.finished_ok.emit(model)
