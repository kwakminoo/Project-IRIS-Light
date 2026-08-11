"""고정(pin)된 모니터링 대상 관리 — 최대 3개.

hwnd는 앱을 다시 켜면 달라지므로 영속화는 창 제목으로 한다.
실제 캡처 대상은 매 갱신마다 제목으로 현재 창 목록에서 다시 찾는다."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from iris.monitoring.models import StatusCategory

if TYPE_CHECKING:
    from iris.storage.database import Database

MAX_PINS = 3
_PREF_KEY = "monitor.pinned_titles"


@dataclass
class PinnedTarget:
    """고정된 창 하나의 현재 상태."""

    title: str
    hwnd: int = 0
    status: StatusCategory = StatusCategory.UNKNOWN
    confidence: float = 0.0
    reason: str = ""
    recommended_action: str = ""
    last_checked_at: str = ""
    analyzing: bool = False


class PinStore:
    """고정 목록 + 최신 분석 결과. 스레드 안전.

    UI(메인 스레드)와 분석 워커(데몬 스레드)가 같이 읽고 쓰므로 락으로 감싼다."""

    def __init__(self, db: Optional["Database"] = None) -> None:
        self._db = db
        self._lock = threading.RLock()
        self._pins: dict[str, PinnedTarget] = {}  # key: 소문자 제목
        self._load()

    # ------------------------------------------------------------------
    # 고정 / 해제
    # ------------------------------------------------------------------

    @staticmethod
    def _key(title: str) -> str:
        return (title or "").strip().lower()

    def is_pinned(self, title: str) -> bool:
        with self._lock:
            return self._key(title) in self._pins

    def is_full(self) -> bool:
        with self._lock:
            return len(self._pins) >= MAX_PINS

    def count(self) -> int:
        with self._lock:
            return len(self._pins)

    def pin(self, title: str, hwnd: int = 0) -> bool:
        """고정. 이미 고정됐거나 정원(3개)이 찼으면 False."""
        key = self._key(title)
        if not key:
            return False
        with self._lock:
            if key in self._pins:
                return False
            if len(self._pins) >= MAX_PINS:
                return False
            self._pins[key] = PinnedTarget(title=title.strip(), hwnd=int(hwnd or 0))
            self._save()
        return True

    def unpin(self, title: str) -> bool:
        key = self._key(title)
        with self._lock:
            if key not in self._pins:
                return False
            del self._pins[key]
            self._save()
        return True

    def toggle(self, title: str, hwnd: int = 0) -> tuple[bool, str]:
        """(성공 여부, 사유). 실패 사유는 UI 안내용."""
        if self.is_pinned(title):
            self.unpin(title)
            return True, "unpinned"
        if self.is_full():
            return False, "full"
        if not self.pin(title, hwnd):
            return False, "invalid"
        return True, "pinned"

    # ------------------------------------------------------------------
    # 조회 / 갱신
    # ------------------------------------------------------------------

    def list_pins(self) -> list[PinnedTarget]:
        with self._lock:
            return [
                PinnedTarget(**vars(t)) for t in self._pins.values()
            ]  # 사본 — 워커가 들고 있는 동안 바뀌지 않도록

    def get(self, title: str) -> Optional[PinnedTarget]:
        with self._lock:
            t = self._pins.get(self._key(title))
            return PinnedTarget(**vars(t)) if t else None

    def set_hwnd(self, title: str, hwnd: int) -> None:
        with self._lock:
            t = self._pins.get(self._key(title))
            if t is not None:
                t.hwnd = int(hwnd or 0)

    def set_analyzing(self, title: str, analyzing: bool) -> None:
        with self._lock:
            t = self._pins.get(self._key(title))
            if t is not None:
                t.analyzing = analyzing

    def update_result(
        self,
        title: str,
        status: StatusCategory,
        confidence: float,
        reason: str,
        recommended_action: str,
        checked_at: str,
    ) -> Optional[StatusCategory]:
        """분석 결과 반영. 직전 상태를 반환(변화 감지용, 처음이면 None)."""
        with self._lock:
            t = self._pins.get(self._key(title))
            if t is None:
                return None
            previous = t.status if t.last_checked_at else None
            t.status = status
            t.confidence = confidence
            t.reason = reason
            t.recommended_action = recommended_action
            t.last_checked_at = checked_at
            t.analyzing = False
            return previous

    # ------------------------------------------------------------------
    # 영속화 — user_preferences에 제목 목록만
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._db is None:
            return
        try:
            raw = self._db.get_preference(_PREF_KEY, "")
            titles = json.loads(raw) if raw else []
        except Exception:
            return
        if not isinstance(titles, list):
            return
        with self._lock:
            for title in titles[:MAX_PINS]:
                key = self._key(str(title))
                if key:
                    self._pins[key] = PinnedTarget(title=str(title).strip())

    def _save(self) -> None:
        """호출 측이 이미 락을 잡고 있어야 한다."""
        if self._db is None:
            return
        try:
            self._db.set_preference(
                _PREF_KEY, json.dumps([t.title for t in self._pins.values()])
            )
        except Exception:
            pass
