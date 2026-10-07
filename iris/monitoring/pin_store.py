"""고정(pin)된 모니터링 대상 관리 — 최대 3개.

핀의 이름(키)은 고정할 때의 창 제목이다. 하지만 브라우저·편집기 제목은 탭이나
파일을 바꿀 때마다 바뀌므로, 실제 창은 hwnd 로 먼저 찾고 제목은 그다음이다.
hwnd 도 함께 저장한다 — IRIS 만 다시 켠 경우 대상 창은 그대로 살아 있다."""

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
    # 지금 그 창에 떠 있는 제목 (탭을 바꾸면 고정할 때 제목과 달라진다)
    current_title: str = ""
    summary: str = ""


def _app_suffix(title: str) -> str:
    """'문서 - Google Chrome' → 'google chrome'. 구분자가 없으면 빈 문자열."""
    for sep in (" - ", " — ", " – "):
        if sep in title:
            return title.rsplit(sep, 1)[1].strip().lower()
    return ""


def _saved_hwnd_still_valid(hwnd: int, title: str) -> bool:
    """지난 세션에 저장한 hwnd 가 아직 그 창인지.

    창을 닫거나 재부팅하면 Windows 가 같은 번호를 엉뚱한 창에 다시 준다 — 그대로 믿으면
    다른 앱 화면을 분석해 알린다. 제목이 같거나 같은 앱(제목 끝)일 때만 믿는다."""
    import sys

    if not hwnd or sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        if not user32.IsWindow(hwnd):
            return False
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        now = buf.value.strip()
    except Exception:
        return False
    if now.lower() == title.strip().lower():
        return True
    suffix = _app_suffix(title)
    return bool(suffix) and _app_suffix(now) == suffix


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

    def _match_locked(self, title: str, hwnd: int) -> Optional[PinnedTarget]:
        if hwnd:
            for t in self._pins.values():
                if t.hwnd and t.hwnd == int(hwnd):
                    return t
        return self._pins.get(self._key(title))

    def match(self, title: str, hwnd: int = 0) -> Optional[PinnedTarget]:
        """창 하나가 어느 핀인지 — hwnd 가 같으면 제목이 바뀌었어도 같은 창이다."""
        with self._lock:
            t = self._match_locked(title, hwnd)
            return PinnedTarget(**vars(t)) if t else None

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
        self._register_target(title.strip(), hwnd)
        return True

    def unpin(self, title: str) -> bool:
        key = self._key(title)
        with self._lock:
            if key not in self._pins:
                return False
            del self._pins[key]
            self._save()
        self._disable_target(title)
        return True

    def toggle(self, title: str, hwnd: int = 0) -> tuple[bool, str]:
        """(성공 여부, 사유). 실패 사유는 UI 안내용."""
        existing = self.match(title, hwnd)
        if existing is not None:
            self.unpin(existing.title)
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

    def set_hwnd(self, title: str, hwnd: int, current_title: str = "") -> None:
        with self._lock:
            t = self._pins.get(self._key(title))
            if t is None:
                return
            changed = t.hwnd != int(hwnd or 0)
            t.hwnd = int(hwnd or 0)
            if current_title:
                t.current_title = current_title.strip()
            if changed:
                self._save()

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
        summary: str = "",
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
            t.summary = summary
            t.last_checked_at = checked_at
            t.analyzing = False
            persist_title = t.title
        self._persist_status(persist_title, status, reason, checked_at)
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
        restored: list[str] = []
        with self._lock:
            for item in titles[:MAX_PINS]:
                # 예전 형식은 제목 문자열 목록, 지금은 {"title", "hwnd"}
                if isinstance(item, dict):
                    title, hwnd = str(item.get("title") or ""), item.get("hwnd") or 0
                else:
                    title, hwnd = str(item), 0
                key = self._key(title)
                if key:
                    name = title.strip()
                    try:
                        hwnd = int(hwnd)
                    except (TypeError, ValueError):
                        hwnd = 0
                    if not _saved_hwnd_still_valid(hwnd, name):
                        hwnd = 0
                    self._pins[key] = PinnedTarget(title=name, hwnd=hwnd)
                    restored.append(name)
        # 재시작 후에도 카드가 지난 세션의 마지막 상태를 보여줄 수 있도록 되살린다
        for name in restored:
            self._register_target(name, 0)
        self._restore_last_status(restored)

    # ------------------------------------------------------------------
    # targets 테이블 연동
    #
    # 이 연동이 없으면 targets 는 영원히 비어 있고,
    # unified_monitor_panel 의 "상태: …" 블록이 한 번도 그려지지 않는다.
    # DB 실패가 감시 기능 자체를 멈추면 안 되므로 전부 삼킨다.
    # ------------------------------------------------------------------

    def _register_target(self, title: str, hwnd: int) -> None:
        if self._db is None:
            return
        try:
            self._db.upsert_target(
                title,
                kind="desktop_window",
                handle=str(int(hwnd or 0)),
                enabled=True,
            )
        except Exception:
            pass

    def _disable_target(self, title: str) -> None:
        if self._db is None:
            return
        try:
            self._db.set_target_enabled_by_title(title, False)
        except Exception:
            pass

    def _persist_status(
        self, title: str, status: StatusCategory, reason: str, checked_at: str
    ) -> None:
        if self._db is None:
            return
        try:
            self._db.update_target_status(
                title,
                status=status.value,
                last_event=reason or "",
                last_checked_at=checked_at or "",
            )
        except Exception:
            pass

    def _restore_last_status(self, titles: list[str]) -> None:
        """지난 세션의 마지막 분석 결과를 메모리 핀에 되살린다.

        analyzing 은 켜지 않는다 — 실제 분석은 워커가 다시 돌 때 갱신된다."""
        if self._db is None or not titles:
            return
        try:
            rows = self._db.list_targets(True)
        except Exception:
            return
        by_title = {}
        for row in rows:
            try:
                by_title[self._key(str(row["title"] or ""))] = row
            except Exception:
                continue
        with self._lock:
            for name in titles:
                key = self._key(name)
                target = self._pins.get(key)
                row = by_title.get(key)
                if target is None or row is None:
                    continue
                try:
                    target.status = StatusCategory(str(row["status"] or "UNKNOWN"))
                except ValueError:
                    target.status = StatusCategory.UNKNOWN
                except Exception:
                    continue
                try:
                    target.reason = str(row["last_event"] or "")
                    target.last_checked_at = str(row["last_checked_at"] or "")
                except Exception:
                    pass

    def _save(self) -> None:
        """호출 측이 이미 락을 잡고 있어야 한다."""
        if self._db is None:
            return
        try:
            self._db.set_preference(
                _PREF_KEY,
                json.dumps(
                    [{"title": t.title, "hwnd": t.hwnd} for t in self._pins.values()],
                    ensure_ascii=False,
                ),
            )
        except Exception:
            pass
