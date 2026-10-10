"""모델 전환 오케스트레이터 — UI가 부르는 단일 진입점.

History 기록 · 위키 RAG 검색 · 컨텍스트 아카이브 · 인수인계문을 한 데 묶는다.
UI 위젯도 HTTP 클라이언트도 여기서 import 하지 않는다. 구 모델에게 요약을
시키는 일은 `summarizer` 콜러블로 주입받는다 — 그래야 Ollama·Hermes·커스텀 API
어느 백엔드로 붙어도 이 모듈이 그대로 쓰인다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from iris.knowledge.history_index import (
    _VEC_MARGIN,
    Embedder,
    OllamaEmbedder,
    SearchHit,
    format_hits_for_prompt,
    index_entry,
    search,
)
from iris.knowledge.history_store import (
    KIND_ACTION,
    KIND_CHAT,
    HistoryEntry,
    record_entry,
)
from iris.knowledge.iris_wiki import IrisWiki
from iris.runtime.context_archive import (
    ArchiveRetention,
    DEFAULT_RETENTION,
    create_snapshot,
    fail_snapshot,
    finalize_snapshot,
    lineage,
    lineage_messages,
    new_session_token,
)
from iris.runtime.context_handoff import (
    HandoffContext,
    build_successor_messages,
    compact_handoff_task,
    deterministic_handoff,
    history_replay_task,
    select_tail_messages,
)
from iris.runtime.model_failover import (
    ExecutionPlan,
    RouteTarget,
    build_execution_plan,
    describe_switch,
    should_preempt,
)
from iris.storage.database import Database
from iris.storage.failover_prefs import (
    FailoverSettings,
    HistorySettings,
    load_failover_settings,
    load_history_settings,
)

# (model, messages) -> 요약 텍스트. 실패하면 예외를 던지거나 빈 문자열을 준다.
Summarizer = Callable[[str, list[dict[str, str]]], str]


# 앱이 쓰는 임베딩 요청은 모두 이 시간만큼 모델을 붙잡아 둔다. 기본 5분이면
# 잠깐 쉬었다 보낸 첫 메시지마다 콜드 로드(실측 9초, 채팅 모델과 겹치면 60초)를
# 탄다. 30분이면 대화하는 동안은 떠 있고, 안 쓰면 GPU 664MB를 돌려준다.
EMBED_KEEP_ALIVE = "30m"


def resolve_embedder(
    settings: HistorySettings, ollama_client: object | None
) -> Embedder | None:
    """설정 + 설치된 Ollama 모델로 임베더를 고른다. 못 고르면 None(키워드 검색만)."""
    if not settings.enabled or not settings.embed_enabled or ollama_client is None:
        return None
    try:
        name = ollama_client.pick_embedding_model(settings.embed_model)  # type: ignore[attr-defined]
    except Exception:
        return None
    if not name:
        return None
    return OllamaEmbedder(client=ollama_client, model_name=name, keep_alive=EMBED_KEEP_ALIVE)


@dataclass
class SwitchResult:
    context: HandoffContext
    messages: list[dict[str, str]]
    notice: str

    @property
    def archive_id(self) -> str:
        return self.context.archive_id


class ModelSwitchService:
    """대화 기록과 모델 전환을 담당한다."""

    def __init__(
        self,
        db: Database,
        *,
        wiki: IrisWiki | None = None,
        embedder: Embedder | None = None,
        retention: ArchiveRetention = DEFAULT_RETENTION,
    ) -> None:
        self.db = db
        self.wiki = wiki
        self.embedder = embedder
        self.retention = retention

    # ---- 설정 --------------------------------------------------------

    @property
    def history_settings(self) -> HistorySettings:
        return load_history_settings(self.db)

    @property
    def failover_settings(self) -> FailoverSettings:
        return load_failover_settings(self.db)

    # ---- 기록 --------------------------------------------------------

    def record(
        self,
        kind: str,
        body: str,
        *,
        title: str = "",
        conversation_id: int = 0,
        role: str = "",
        source: str = "",
        model: str = "",
        tags: str = "",
        rel_path: str = "",
    ) -> HistoryEntry | None:
        """History 한 건 기록 + 즉시 색인. 설정으로 꺼둔 종류는 건너뛴다."""
        settings = self.history_settings
        if not settings.records(kind):
            return None
        entry = record_entry(
            self.db,
            kind=kind,
            body=body,
            title=title,
            conversation_id=conversation_id,
            role=role,
            source=source,
            model=model,
            tags=tags,
            wiki=self.wiki,
            rel_path=rel_path,
        )
        if entry is not None:
            index_entry(self.db, entry, embedder=self.embedder)
        return entry

    def record_turn(
        self, conversation_id: int, role: str, content: str, *, model: str = ""
    ) -> HistoryEntry | None:
        return self.record(
            KIND_CHAT, content, conversation_id=conversation_id, role=role, model=model
        )

    # ---- 검색 --------------------------------------------------------

    def retrieve(
        self,
        query: str,
        *,
        conversation_id: int | None = None,
        limit: int | None = None,
        embedder: Embedder | None = None,
        exclude_conversation_id: int | None = None,
        vector_margin: float | None = _VEC_MARGIN,
    ) -> list[SearchHit]:
        """`embedder` 를 주면 이번 검색에만 그걸 쓴다(없으면 서비스에 붙은 것)."""
        settings = self.history_settings
        if not settings.enabled:
            return []
        count = settings.retrieval_limit if limit is None else int(limit)
        if count <= 0:
            return []
        return search(
            self.db,
            query,
            limit=count,
            embedder=embedder or self.embedder,
            conversation_id=conversation_id,
            exclude_conversation_id=exclude_conversation_id,
            vector_margin=vector_margin,
        )

    def evidence_block(
        self,
        query: str,
        *,
        conversation_id: int | None = None,
        embedder: Embedder | None = None,
    ) -> str:
        return format_hits_for_prompt(
            self.retrieve(query, conversation_id=conversation_id, embedder=embedder)
        )

    def semantic_evidence_block(
        self,
        query: str,
        ollama_client: object | None,
        *,
        conversation_id: int | None = None,
    ) -> str:
        """검색어까지 임베딩하는 근거 묶음. **워커 스레드에서만 부를 것.**

        질의 임베딩은 Ollama 왕복이라 한 번에 1~3초 걸린다(bge-m3 실측). 임베딩
        모델이 없거나 Ollama가 꺼져 있으면 키워드 검색 결과만 돌려준다.
        """
        embedder = resolve_embedder(self.history_settings, ollama_client)
        return self.evidence_block(query, conversation_id=conversation_id, embedder=embedder)

    # ---- 전환 --------------------------------------------------------

    def plan_for(self, primary: RouteTarget) -> ExecutionPlan:
        settings = self.failover_settings
        if not settings.enabled:
            return build_execution_plan(primary, [], mode="off")
        return build_execution_plan(
            primary,
            settings.targets(),
            mode=settings.mode,
            retry_count=settings.retry_count,
        )

    def preempt_check(self, quotas: list[object]) -> tuple[bool, str]:
        settings = self.failover_settings
        if not settings.enabled or not settings.preempt_enabled:
            return False, ""
        return should_preempt(quotas, threshold_percent=settings.preempt_percent)

    def prepare_handoff(
        self,
        conversation_id: int,
        messages: list[dict[str, str]],
        to_target: RouteTarget,
        *,
        from_target: RouteTarget | None = None,
        reason: str = "",
        summarizer: Summarizer | None = None,
        archive: bool = True,
    ) -> SwitchResult:
        """맥락 이관 묶음을 만든다. **기록은 하지 않는다.**

        `archive=False` 면 아카이브 스냅샷도 남기지 않는다. 자동 전환 후보를 미리
        준비할 때 쓴다 — 후보는 매 턴 만들어 두지만 실제로 쓰이는 일은 드물어,
        준비 단계에서 세대를 늘리거나 전환 기록을 남기면 안 된다.
        """
        convo = list(messages or [])
        token = new_session_token()
        archive_id = ""
        generation = 0
        if archive:
            snapshot = create_snapshot(
                self.db,
                conversation_id,
                convo,
                model=(from_target.model if from_target else ""),
                backend=(from_target.backend if from_target else ""),
                session_token=token,
                retention=self.retention,
            )
            archive_id = snapshot.archive_id
            generation = snapshot.generation

        settings = self.failover_settings
        handoff_text = ""
        llm_written = False
        if summarizer is not None and settings.ask_old_model_summary and from_target is not None:
            task = compact_handoff_task(
                archive_id=archive_id,
                session_token=token,
                generation=generation,
                conversation_id=conversation_id,
            )
            try:
                written = summarizer(from_target.model, [*convo, {"role": "user", "content": task}])
            except Exception:
                written = ""
            if (written or "").strip():
                handoff_text = written.strip()
                llm_written = True

        if not handoff_text:
            handoff_text = deterministic_handoff(
                convo,
                archive_id=archive_id,
                session_token=token,
                generation=generation,
                conversation_id=conversation_id,
            )

        wiki_block = ""
        query = retrieval_query(convo)
        if query:
            wiki_block = self.evidence_block(query, conversation_id=None)

        context = HandoffContext(
            handoff_text=handoff_text,
            wiki_block=wiki_block,
            tail_messages=select_tail_messages(convo),
            archive_id=archive_id,
            session_token=token,
            generation=generation,
            from_model=(from_target.label if from_target else ""),
            to_model=to_target.label,
            llm_written=llm_written,
        )
        if archive_id:
            finalize_snapshot(
                self.db, archive_id, model=to_target.model, backend=to_target.backend
            )
        return SwitchResult(
            context=context,
            messages=build_successor_messages(context),
            notice=describe_switch(from_target, to_target, reason),
        )

    def switch(
        self,
        conversation_id: int,
        messages: list[dict[str, str]],
        to_target: RouteTarget,
        *,
        from_target: RouteTarget | None = None,
        reason: str = "",
        summarizer: Summarizer | None = None,
    ) -> SwitchResult:
        """실제로 모델을 갈아탄다 — 원문을 아카이브하고 전환을 History에 남긴다.

        구 모델이 살아있으면 인수인계문을 쓰게 하고, 죽었으면(할당량 소진 등)
        규칙 기반 정리로 대체한다. 어느 쪽이든 원문은 아카이브에 남으므로
        나중에 되찾을 수 있다.
        """
        result = self.prepare_handoff(
            conversation_id,
            messages,
            to_target,
            from_target=from_target,
            reason=reason,
            summarizer=summarizer,
            archive=True,
        )
        context = result.context
        self.record(
            KIND_ACTION,
            "\n".join(
                [
                    result.notice,
                    f"- 아카이브: `{context.archive_id}` (세대 {context.generation})",
                    f"- 인수인계: {'구 모델 작성' if context.llm_written else '자동 정리'}",
                    f"- 원문 보존: {len(messages or [])}턴",
                ]
            ),
            title="모델 전환",
            conversation_id=conversation_id,
            model=to_target.model,
            tags="model-switch",
        )
        return result

    def abandon(self, archive_id: str) -> None:
        """전환이 끝내 실패했다 — 아카이브를 failed 로 표시한다."""
        fail_snapshot(self.db, archive_id)

    # ---- 복원 --------------------------------------------------------

    def replay_request(self, archive_id: str, task: str) -> list[dict[str, str]] | None:
        """요약이 부족할 때 원문 세대에 되묻는 요청을 만든다.

        반환한 messages 를 아무 모델에나 그대로 보내면 된다 — 그 모델은 과거
        원문을 자기 맥락으로 삼아 질문에만 답한다.
        """
        original = lineage_messages(self.db, archive_id)
        if not original:
            return None
        return [*original, {"role": "user", "content": history_replay_task(task)}]

    def lineage_summary(self, archive_id: str) -> str:
        chain = lineage(self.db, archive_id)
        if not chain:
            return "보존된 이전 맥락이 없습니다."
        lines = [f"보존된 맥락 {len(chain)}세대:"]
        for snap in chain:
            label = snap.model or "(모델 미상)"
            lines.append(
                f"- 세대 {snap.generation}: `{label}` · {len(snap.messages)}턴 · {snap.created_at}"
            )
        return "\n".join(lines)


def retrieval_query(messages: list[dict[str, str]], *, turns: int = 3, limit: int = 600) -> str:
    """위키 검색에 쓸 질의문 — 마지막 사용자 발화 몇 개를 합친다.

    마지막 한 마디만 쓰면 "고쳤는데 또 납니다" 같은 대명사뿐인 발화에서 검색어가
    사라진다. 앞선 발화까지 붙여야 주제어가 들어온다.
    """
    said = [
        str(m.get("content") or "").strip()
        for m in (messages or [])
        if str(m.get("role")) == "user" and str(m.get("content") or "").strip()
    ]
    if not said:
        return ""
    picked = said[-max(1, int(turns)) :]
    joined = " ".join(picked)
    return joined if len(joined) <= limit else joined[-limit:]


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from iris.storage.failover_prefs import (
        FallbackEntry,
        save_failover_settings,
        save_history_settings,
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = Database(root / "t.db")
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        svc = ModelSwitchService(db, wiki=wiki)

        old = RouteTarget(model="qwen3:8b", backend="ollama", label="qwen3 8b")
        new = RouteTarget(model="gemma4:free", backend="ollama", label="gemma4", free=True)

        # 기록 + 검색
        svc.record_turn(3, "user", "설치 프로그램에서 권한 오류가 납니다")
        svc.record_turn(3, "assistant", "venv 폴더 소유권을 고치세요", model="qwen3:8b")
        svc.record(KIND_ACTION, "setup.ps1 -Recreate 실행함", title="설치 재시도", conversation_id=3)
        hits = svc.retrieve("권한 오류")
        assert hits and "권한" in hits[0].entry.body
        assert "History 발췌" in svc.evidence_block("권한 오류")

        convo = [
            {"role": "user", "content": "설치 프로그램에서 권한 오류가 납니다"},
            {"role": "assistant", "content": "venv 폴더 소유권을 고치세요"},
            {"role": "user", "content": "고쳤는데 또 납니다"},
        ]

        # 구 모델이 죽은 경우 — 규칙 기반으로 넘어간다
        def _dead(model, messages):
            raise RuntimeError("HTTP 429")

        res = svc.switch(3, convo, new, from_target=old, reason="할당량 소진", summarizer=_dead)
        assert res.context.llm_written is False
        assert "자동 정리" in res.context.summary_line
        assert "할당량 소진" in res.notice and "무료" in res.notice
        assert res.messages[0]["role"] == "system"
        assert "고쳤는데 또 납니다" in res.messages[-1]["content"]
        assert "History 발췌" in res.messages[0]["content"]
        gen1 = res.context.generation

        # 전환 자체가 History에 남는다
        switched = [e for e in svc.retrieve("모델 전환") if e.entry.tags == "model-switch"]
        assert switched, "전환 기록이 검색되지 않음"

        # 구 모델이 살아있는 경우
        def _alive(model, messages):
            assert model == "qwen3:8b"
            assert "아이리스 인수인계 작업" in messages[-1]["content"]
            return "## 1. 현재 목표와 상태\n설치 권한 문제 해결 중"

        res2 = svc.switch(3, convo, new, from_target=old, reason="수동 전환", summarizer=_alive)
        assert res2.context.llm_written is True
        assert "요약 인수인계" in res2.context.summary_line
        assert "설치 권한 문제 해결 중" in res2.messages[0]["content"]
        assert res2.context.generation == gen1 + 1

        # 세대 체인과 원문 복원
        assert "2세대" in svc.lineage_summary(res2.archive_id)
        replay = svc.replay_request(res2.archive_id, "그때 무슨 명령을 실행했지?")
        assert replay is not None
        assert replay[0]["content"] == "설치 프로그램에서 권한 오류가 납니다"  # 최고참 원문
        assert "그때 무슨 명령을 실행했지?" in replay[-1]["content"]
        assert svc.replay_request("없는아카이브", "질문") is None

        # 요약을 끄면 구 모델이 살아있어도 안 부른다
        s = svc.failover_settings
        s.ask_old_model_summary = False
        save_failover_settings(db, s)
        res3 = svc.switch(3, convo, new, from_target=old, summarizer=_alive)
        assert res3.context.llm_written is False

        # 전환 체인 계획
        s = svc.failover_settings
        s.chain = [FallbackEntry(model="gemma4:free"), FallbackEntry(model="llama4:free", backend="api")]
        save_failover_settings(db, s)
        plan = svc.plan_for(old)
        assert [a.target.model for a in plan.attempts] == ["qwen3:8b", "gemma4:free", "llama4:free"]
        s.enabled = False
        save_failover_settings(db, s)
        assert len(svc.plan_for(old).attempts) == 1

        class _Q:
            key, label, percent = "week", "WEEK", 98.0

        assert svc.preempt_check([_Q()])[0] is False  # failover 꺼둔 상태
        s.enabled = True
        save_failover_settings(db, s)
        assert svc.preempt_check([_Q()])[0] is True

        # History를 통째로 끄면 기록도 검색도 멈춘다
        hs = svc.history_settings
        hs.enabled = False
        save_history_settings(db, hs)
        assert svc.record_turn(3, "user", "안 남을 말") is None
        assert svc.retrieve("권한") == []
        assert resolve_embedder(hs, object()) is None

        db.close()

    print("model_switch self-check ok")
