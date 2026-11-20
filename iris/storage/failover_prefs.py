"""모델 자동 전환·History 기록 설정 — user_preferences JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from iris.runtime.model_failover import (
    DEFAULT_PREEMPT_PERCENT,
    MODE_MODEL_CHAIN,
    RouteTarget,
    normalize_mode,
)
from iris.storage.database import Database

FAILOVER_KEY = "model_failover_v1"
HISTORY_KEY = "wiki_history_v1"

BACKENDS: tuple[str, ...] = ("ollama", "agent", "api")


@dataclass
class FallbackEntry:
    model: str = ""
    backend: str = "ollama"
    label: str = ""
    free: bool = True

    def __post_init__(self) -> None:
        self.model = str(self.model or "").strip()
        self.backend = str(self.backend or "ollama").strip().lower()
        if self.backend == "hermes":
            self.backend = "agent"
        if self.backend not in BACKENDS:
            self.backend = "ollama"
        self.label = str(self.label or "").strip() or self.model
        self.free = bool(self.free)

    def to_target(self) -> RouteTarget:
        return RouteTarget(
            model=self.model, backend=self.backend, label=self.label, free=self.free
        )


@dataclass
class FailoverSettings:
    enabled: bool = True
    mode: str = MODE_MODEL_CHAIN
    retry_count: int = 2
    preempt_percent: float = DEFAULT_PREEMPT_PERCENT
    preempt_enabled: bool = True
    # 전환할 때 구 모델에게 인수인계문을 쓰게 할지. 꺼도 규칙 기반 정리는 남는다.
    ask_old_model_summary: bool = True
    chain: list[FallbackEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.enabled = bool(self.enabled)
        self.mode = normalize_mode(self.mode)
        self.retry_count = max(0, min(10, int(self.retry_count or 0)))
        try:
            pct = float(self.preempt_percent)
        except (TypeError, ValueError):
            pct = DEFAULT_PREEMPT_PERCENT
        self.preempt_percent = max(50.0, min(100.0, pct))
        self.preempt_enabled = bool(self.preempt_enabled)
        self.ask_old_model_summary = bool(self.ask_old_model_summary)
        cleaned: list[FallbackEntry] = []
        seen: set[str] = set()
        for item in self.chain or []:
            entry = item if isinstance(item, FallbackEntry) else FallbackEntry(**dict(item))
            if not entry.model:
                continue
            key = f"{entry.backend}|{entry.model}"
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(entry)
        self.chain = cleaned

    def targets(self) -> list[RouteTarget]:
        return [e.to_target() for e in self.chain]


@dataclass
class HistorySettings:
    """위키 History 기록·검색 설정."""

    enabled: bool = True
    record_chat: bool = True
    record_actions: bool = True
    record_artifacts: bool = True
    record_inputs: bool = True
    # 검색 결과를 몇 건이나 모델에게 붙일지
    retrieval_limit: int = 5
    # 임베딩 모델. 빈 값이면 설치된 것 중 자동 선택, 없으면 키워드 검색만.
    embed_model: str = ""
    embed_enabled: bool = True
    # 평소 채팅에서 다른(이전) 대화의 기록을 찾아 참고한다. 참고한 기록은
    # 답변 위에 출처로 표시되므로 사용자가 보고 끌 수 있다.
    reference_past_chats: bool = True

    def __post_init__(self) -> None:
        self.enabled = bool(self.enabled)
        self.record_chat = bool(self.record_chat)
        self.record_actions = bool(self.record_actions)
        self.record_artifacts = bool(self.record_artifacts)
        self.record_inputs = bool(self.record_inputs)
        self.retrieval_limit = max(0, min(20, int(self.retrieval_limit or 0)))
        self.embed_model = str(self.embed_model or "").strip()
        self.embed_enabled = bool(self.embed_enabled)
        self.reference_past_chats = bool(self.reference_past_chats)

    def records(self, kind: str) -> bool:
        if not self.enabled:
            return False
        return {
            "chat": self.record_chat,
            "action": self.record_actions,
            "artifact": self.record_artifacts,
            "input": self.record_inputs,
            "episode": True,
        }.get(kind, True)


def _load_json(db: Database, key: str) -> dict:
    raw = (db.get_preference(key, "") or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def load_failover_settings(db: Database) -> FailoverSettings:
    data = _load_json(db, FAILOVER_KEY)
    try:
        return FailoverSettings(**data) if data else FailoverSettings()
    except TypeError:
        # 설정 형식이 바뀐 옛 값 — 기본값으로 되돌린다
        return FailoverSettings()


def save_failover_settings(db: Database, settings: FailoverSettings) -> None:
    db.set_preference(FAILOVER_KEY, json.dumps(asdict(settings), ensure_ascii=False))


def load_history_settings(db: Database) -> HistorySettings:
    data = _load_json(db, HISTORY_KEY)
    try:
        return HistorySettings(**data) if data else HistorySettings()
    except TypeError:
        return HistorySettings()


def save_history_settings(db: Database, settings: HistorySettings) -> None:
    db.set_preference(HISTORY_KEY, json.dumps(asdict(settings), ensure_ascii=False))


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    s = FailoverSettings(mode="이상한값", retry_count=99, preempt_percent=1000)
    assert s.mode == MODE_MODEL_CHAIN and s.retry_count == 10 and s.preempt_percent == 100.0
    assert FailoverSettings(preempt_percent=10).preempt_percent == 50.0
    assert FailoverSettings(preempt_percent="쓰레기").preempt_percent == DEFAULT_PREEMPT_PERCENT

    dupes = FailoverSettings(
        chain=[
            {"model": "a", "backend": "ollama"},
            {"model": "a", "backend": "ollama"},  # 중복 제거
            {"model": "a", "backend": "api"},  # 백엔드 다르면 남는다
            {"model": "  ", "backend": "ollama"},  # 빈 모델 제거
            {"model": "b", "backend": "없는백엔드"},  # ollama 로 교정
        ]
    )
    assert [(e.model, e.backend) for e in dupes.chain] == [
        ("a", "ollama"), ("a", "api"), ("b", "ollama")
    ]
    assert dupes.chain[0].label == "a"
    targets = dupes.targets()
    assert targets[0].backend == "ollama" and targets[0].free is True

    h = HistorySettings(retrieval_limit=999, record_actions=False)
    assert h.retrieval_limit == 20
    assert h.records("chat") is True and h.records("action") is False
    assert HistorySettings(enabled=False).records("chat") is False
    assert HistorySettings().records("episode") is True

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "t.db")
        assert load_failover_settings(db).enabled is True
        assert load_failover_settings(db).chain == []

        save_failover_settings(db, dupes)
        back = load_failover_settings(db)
        assert [(e.model, e.backend) for e in back.chain] == [
            ("a", "ollama"), ("a", "api"), ("b", "ollama")
        ]

        save_history_settings(db, h)
        assert load_history_settings(db).record_actions is False
        assert load_history_settings(db).retrieval_limit == 20

        # 깨진 JSON·낯선 필드가 들어와도 기본값으로 살아난다
        db.set_preference(FAILOVER_KEY, "{망가짐")
        assert load_failover_settings(db).mode == MODE_MODEL_CHAIN
        db.set_preference(HISTORY_KEY, '{"없는필드": 1}')
        assert load_history_settings(db).enabled is True
        db.close()

    print("failover_prefs self-check ok")
