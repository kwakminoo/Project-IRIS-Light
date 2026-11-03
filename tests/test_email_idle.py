"""IMAP IDLE 파싱·seq 범위·UI prepend 단위 테스트."""

from __future__ import annotations

from iris.infrastructure.email_client import (
    MailSummary,
    fetch_summaries_seq_range,
    parse_exists_line,
)
from iris.ui.workspaces.email_workspace_page import EmailWorkspacePage


def test_parse_exists_line() -> None:
    assert parse_exists_line(b"* 1 EXISTS") == 1
    assert parse_exists_line(b"* 105 EXISTS\r\n") == 105
    assert parse_exists_line(b"* 0 EXISTS") == 0
    assert parse_exists_line(b"* OK Still here") is None
    assert parse_exists_line(b"* 3 RECENT") is None


def test_fetch_summaries_seq_range_newest_first() -> None:
    from email.message import EmailMessage

    class _FakeMail:
        def fetch(self, seq, _parts):  # noqa: ANN001
            n = seq.decode()
            msg = EmailMessage()
            msg["From"] = f"a{n}@t"
            msg["Subject"] = f"S{n}"
            msg["Date"] = "Sat, 18 Oct 2026 12:00:00 +0900"
            msg.set_content(f"body{n}")
            return "OK", [(b"x", msg.as_bytes())]

    items = fetch_summaries_seq_range(_FakeMail(), after_seq=10, new_exists=13)
    assert [m.uid for m in items] == ["13", "12", "11"]
    assert items[0].subject == "S13"
    assert fetch_summaries_seq_range(_FakeMail(), 13, 13) == []


def test_prepend_mails_dedupes_and_keeps_order() -> None:
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication.instance() or QApplication(sys.argv)
    page = EmailWorkspacePage()
    older = [
        MailSummary("1", "old", "a", "2026-10-17 10:00", "x"),
        MailSummary("2", "older", "b", "2026-10-16 09:00", "y"),
    ]
    page.set_mails(older, has_more=False)
    page.prepend_mails(
        [
            MailSummary("3", "new", "c", "2026-10-18 11:00", "z"),
            MailSummary("1", "dup", "a", "2026-10-17 10:00", "x"),
        ]
    )
    uids = [m.uid for m in page.current_mails()]
    assert uids == ["3", "1", "2"]
    del app
