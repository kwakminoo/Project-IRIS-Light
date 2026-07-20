"""알림 쿨다운·무시·스누즈·대상 비활성 정책 (SQLite)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from iris.storage.database import Database


class NotificationPolicy:
    """notification_prefs / notification_log 연동."""

    def __init__(self, db: "Database", default_cooldown_seconds: float = 90.0) -> None:
        self._db = db
        self._default_cooldown = default_cooldown_seconds

    def should_suppress(self, target_id: int, category: str) -> Optional[str]:
        """
        알림을 막으면 이유 문자열, 표시 가능하면 None.
        """
        if self._db.is_target_notification_disabled(target_id):
            return "target_disabled"
        if self._db.is_notification_ignored(target_id, category):
            return "ignored"
        snooze = self._db.get_notification_snooze_until(target_id, category)
        if snooze:
            try:
                until = datetime.fromisoformat(snooze.replace("Z", "+00:00"))
                now = datetime.utcnow()
                if until.tzinfo is not None:
                    until = until.replace(tzinfo=None)
                if now < until:
                    return "snoozed"
            except ValueError:
                pass
        cooldown = self._db.get_notification_cooldown_seconds(
            target_id, category, self._default_cooldown
        )
        last = self._db.get_last_notification_shown_at(target_id, category)
        if last:
            try:
                shown = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if shown.tzinfo is not None:
                    shown = shown.replace(tzinfo=None)
                age = (datetime.utcnow() - shown).total_seconds()
                if age < cooldown:
                    return "cooldown"
            except ValueError:
                pass
        return None

    def mark_shown(self, target_id: int, category: str) -> None:
        self._db.set_last_notification_shown_at(target_id, category)

    def dismiss_permanently(self, target_id: int, category: str) -> None:
        self._db.set_notification_pref("ignore", "1", target_id=target_id, category=category)

    def snooze(self, target_id: int, category: str, minutes: int = 15) -> None:
        from datetime import timedelta

        until = (datetime.utcnow() + timedelta(minutes=minutes)).isoformat()
        self._db.set_notification_pref("snooze_until", until, target_id=target_id, category=category)

    def disable_target(self, target_id: int) -> None:
        self._db.set_notification_pref("disabled", "1", target_id=target_id, category="")
        self._db.set_target_enabled(target_id, False)

    def log_notification(
        self,
        target_id: int | None,
        event_id: int | None,
        category: str,
        title: str,
        message: str,
        user_decision: str = "shown",
    ) -> int:
        return self._db.insert_notification_log(
            target_id, event_id, category, title, message, user_decision
        )
